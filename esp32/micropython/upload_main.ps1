param(
    [string]$PortName = "COM3",
    [string]$SourcePath = "$PSScriptRoot\main.py"
)

$ErrorActionPreference = "Stop"

function Read-SerialUntil {
    param(
        [System.IO.Ports.SerialPort]$Port,
        [string]$Expected,
        [int]$TimeoutMs = 5000
    )

    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
    $text = ""
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Port.BytesToRead -gt 0) {
            $text += $Port.ReadExisting()
            if ($text.Contains($Expected)) {
                return $text
            }
        }
        Start-Sleep -Milliseconds 20
    }
    throw "Timed out waiting for ESP32 response. Received: $text"
}

function Invoke-RawCommand {
    param(
        [System.IO.Ports.SerialPort]$Port,
        [string]$Command,
        [int]$TimeoutMs = 5000
    )

    $bytes = [Text.Encoding]::UTF8.GetBytes($Command)
    $Port.Write($bytes, 0, $bytes.Length)
    $Port.Write([byte[]](4), 0, 1)
    $response = Read-SerialUntil -Port $Port -Expected ">" -TimeoutMs $TimeoutMs
    if (-not $response.StartsWith("OK")) {
        throw "ESP32 command failed: $response"
    }
    if ($response -match "Traceback") {
        throw "ESP32 reported an error: $response"
    }
    return $response
}

if (-not (Test-Path -LiteralPath $SourcePath)) {
    throw "Source file not found: $SourcePath"
}

$serial = [System.IO.Ports.SerialPort]::new($PortName, 115200, "None", 8, "One")
$serial.ReadTimeout = 500
$serial.WriteTimeout = 3000
$serial.DtrEnable = $false
$serial.RtsEnable = $false

try {
    $serial.Open()
    Start-Sleep -Milliseconds 300
    $serial.DiscardInBuffer()

    # Stop main.py. Some running serial loops need separated interrupt bytes.
    foreach ($attempt in 1..5) {
        $serial.Write([byte[]](3), 0, 1)
        Start-Sleep -Milliseconds 250
    }
    Start-Sleep -Milliseconds 500
    $interruptOutput = $serial.ReadExisting()

    # Enter raw REPL only after the running program has been interrupted.
    $serial.Write([byte[]](1), 0, 1)
    $banner = Read-SerialUntil -Port $serial -Expected ">" -TimeoutMs 5000
    if (-not $banner.Contains("raw REPL")) {
        throw "Could not enter MicroPython raw REPL. Interrupt output: $interruptOutput Banner: $banner"
    }

    Invoke-RawCommand -Port $serial -Command "import ubinascii" | Out-Null
    Invoke-RawCommand -Port $serial -Command "f=open('main_new.py','wb')" | Out-Null

    $content = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $SourcePath))
    $offset = 0
    while ($offset -lt $content.Length) {
        $count = [Math]::Min(240, $content.Length - $offset)
        $chunk = [byte[]]::new($count)
        [Array]::Copy($content, $offset, $chunk, 0, $count)
        $base64 = [Convert]::ToBase64String($chunk)
        Invoke-RawCommand -Port $serial -Command "f.write(ubinascii.a2b_base64('$base64'))" | Out-Null
        $offset += $count
        Write-Progress -Activity "Uploading main.py" -Status "$offset / $($content.Length) bytes" -PercentComplete (($offset * 100) / $content.Length)
    }
    Invoke-RawCommand -Port $serial -Command "f.close()" | Out-Null

    # Compile on the ESP32 before replacing the running file.
    Invoke-RawCommand -Port $serial -Command "compile(open('main_new.py').read(),'main_new.py','exec');print('SYNTAX_OK')" | Out-Null
    $replace = @"
import os
try:
 os.remove('main_backup.py')
except OSError:
 pass
try:
 os.rename('main.py','main_backup.py')
except OSError:
 pass
os.rename('main_new.py','main.py')
print(os.stat('main.py')[6])
"@
    $result = Invoke-RawCommand -Port $serial -Command $replace
    Write-Host "ESP32 main.py replaced successfully. Response: $result"

    # Soft reset. The new main.py starts automatically.
    $serial.Write([byte[]](4), 0, 1)
    Start-Sleep -Seconds 4
    $startup = $serial.ReadExisting()
    Write-Host "ESP32 startup output:"
    Write-Host $startup
}
finally {
    if ($serial.IsOpen) {
        $serial.Close()
    }
    $serial.Dispose()
}
