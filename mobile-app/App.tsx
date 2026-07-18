// ===== 앱 코드 (Expo React Native) =====
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { StatusBar } from "expo-status-bar";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

const SERVER_URL = process.env.EXPO_PUBLIC_SERVER_URL?.replace(/\/$/, "");
const USER_ID = process.env.EXPO_PUBLIC_USER_ID;

type Spot = {
  id: string;
  label: string;
  vehicleNumber: string | null;
  deviceId: string | null;
  lastSeenAt: string | null;
  temperatureC: number | null;
  humidityPct: number | null;
  outsideTemperatureC: number | null;
  outsideObjectTemperatureC: number | null;
  insideOutsideDeltaC: number | null;
};

type FireAlert = {
  id: string;
  parkingSpotId: string;
  reason: string;
  temperatureC: number;
  humidityPct: number | null;
  outsideTemperatureC: number | null;
  insideOutsideDeltaC: number | null;
  startedAt: string;
  status: "active";
};

type Dashboard = {
  user: { id: string; name: string };
  spots: Spot[];
  activeAlerts: FireAlert[];
};

async function registerForPush(): Promise<string | null> {
  if (!Device.isDevice) {
    console.log("푸시 알림은 실제 휴대전화에서 테스트하세요.");
    return null;
  }
  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== "granted") {
    status = (await Notifications.requestPermissionsAsync()).status;
  }
  if (status !== "granted") return null;

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("fire-alerts", {
      name: "화재 긴급 알림",
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 500, 250, 500],
      sound: "default",
    });
  }

  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  if (!projectId || projectId === "YOUR_EXPO_PROJECT_ID") {
    console.warn("app.json에 Expo projectId를 설정해야 푸시 토큰을 받을 수 있습니다.");
    return null;
  }
  return (await Notifications.getExpoPushTokenAsync({ projectId })).data;
}

export default function App() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    if (!SERVER_URL || !USER_ID) {
      setError(".env에 SERVER_URL과 USER_ID를 설정하세요.");
      setLoading(false);
      return;
    }
    try {
      const response = await fetch(`${SERVER_URL}/api/users/${USER_ID}/dashboard`);
      if (!response.ok) throw new Error(`서버 응답 ${response.status}`);
      setDashboard(await response.json());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "서버 연결 실패");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
    const timer = setInterval(loadDashboard, 3000);
    return () => clearInterval(timer);
  }, [loadDashboard]);

  useEffect(() => {
    if (!SERVER_URL || !USER_ID) return;
    registerForPush()
      .then(async (token) => {
        if (!token) return;
        const response = await fetch(`${SERVER_URL}/api/push/register`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ userId: USER_ID, token, platform: Platform.OS }),
        });
        if (!response.ok) throw new Error(`푸시 등록 실패 ${response.status}`);
      })
      .catch((caught) => console.warn(caught));

    const subscription = Notifications.addNotificationResponseReceivedListener((response) => {
      const spot = response.notification.request.content.data.parkingSpotId;
      if (spot) Alert.alert("화재 경보", `${spot} 구역의 상세 상태를 확인하세요.`);
      loadDashboard();
    });
    return () => subscription.remove();
  }, [loadDashboard]);

  if (loading) {
    return <SafeAreaView style={styles.center}><ActivityIndicator size="large" color="#dc2626" /></SafeAreaView>;
  }

  const hasAlert = (dashboard?.activeAlerts.length ?? 0) > 0;
  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <ScrollView
        contentContainerStyle={styles.container}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); loadDashboard(); }} />}
      >
        <Text style={styles.eyebrow}>EV FIRE SAFETY</Text>
        <Text style={styles.title}>{dashboard?.user.name ?? "사용자"}님의 차량</Text>

        <View style={[styles.banner, hasAlert ? styles.dangerBanner : styles.safeBanner]}>
          <Text style={styles.bannerIcon}>{hasAlert ? "!" : "✓"}</Text>
          <View style={styles.flex}>
            <Text style={[styles.bannerTitle, hasAlert && styles.whiteText]}>
              {hasAlert ? "화재 위험 감지" : "현재 안전합니다"}
            </Text>
            <Text style={[styles.bannerText, hasAlert && styles.whiteText]}>
              {hasAlert ? "차단막 및 펌프 작동 명령이 전달되었습니다." : "주차 구역을 실시간 확인하고 있습니다."}
            </Text>
          </View>
        </View>

        {error && <View style={styles.errorBox}><Text style={styles.errorText}>{error}</Text></View>}

        {dashboard?.activeAlerts.map((alert) => (
          <View key={alert.id} style={styles.alertCard}>
            <Text style={styles.alertLabel}>긴급 · {alert.parkingSpotId}</Text>
            <Text style={styles.alertTemp}>{Number(alert.temperatureC).toFixed(1)}°C</Text>
            <Text style={styles.alertBody}>감지 시각 {new Date(alert.startedAt).toLocaleString("ko-KR")}</Text>
            <Text style={styles.alertBody}>차량에 접근하지 말고 현장 안내와 119 지시에 따르세요.</Text>
          </View>
        ))}

        <Text style={styles.sectionTitle}>내 주차 구역</Text>
        {dashboard?.spots.map((spot) => {
          const online = spot.lastSeenAt && Date.now() - new Date(spot.lastSeenAt).getTime() < 15_000;
          return (
            <View key={spot.id} style={styles.spotCard}>
              <View style={styles.row}>
                <View>
                  <Text style={styles.spotName}>{spot.label}</Text>
                  <Text style={styles.vehicle}>{spot.vehicleNumber ?? "차량 미등록"}</Text>
                </View>
                <Text style={online ? styles.online : styles.offline}>{online ? "● 연결됨" : "● 연결 끊김"}</Text>
              </View>
              <View style={styles.metrics}>
                <View style={styles.metric}>
                  <Text style={styles.metricLabel}>온도</Text>
                  <Text style={styles.metricValue}>{spot.temperatureC == null ? "—" : `${Number(spot.temperatureC).toFixed(1)}°C`}</Text>
                </View>
                <View style={styles.metric}>
                  <Text style={styles.metricLabel}>외부 기준</Text>
                  <Text style={styles.metricValue}>{spot.outsideTemperatureC == null ? "—" : `${Number(spot.outsideTemperatureC).toFixed(1)}°C`}</Text>
                </View>
                <View style={styles.metric}>
                  <Text style={styles.metricLabel}>온도 차이</Text>
                  <Text style={styles.metricValue}>{spot.insideOutsideDeltaC == null ? "—" : `${Number(spot.insideOutsideDeltaC).toFixed(1)}°C`}</Text>
                </View>
                <View style={styles.metric}>
                  <Text style={styles.metricLabel}>습도</Text>
                  <Text style={styles.metricValue}>{spot.humidityPct == null ? "—" : `${Number(spot.humidityPct).toFixed(1)}%`}</Text>
                </View>
              </View>
            </View>
          );
        })}
        <Text style={styles.footer}>화재 위험 시 차량에 접근하지 마세요. 이 앱은 시연용 프로토타입입니다.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#f4f4f0" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f4f4f0" },
  container: { padding: 22, paddingTop: 34, paddingBottom: 40 },
  eyebrow: { color: "#dc2626", fontWeight: "800", fontSize: 12, letterSpacing: 2 },
  title: { color: "#171717", fontSize: 29, fontWeight: "800", marginTop: 5, marginBottom: 22 },
  banner: { flexDirection: "row", alignItems: "center", borderRadius: 18, padding: 18, marginBottom: 16 },
  safeBanner: { backgroundColor: "#dcfce7" },
  dangerBanner: { backgroundColor: "#b91c1c" },
  bannerIcon: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#ffffff", textAlign: "center", lineHeight: 42, color: "#b91c1c", fontWeight: "900", fontSize: 22, marginRight: 13 },
  flex: { flex: 1 },
  bannerTitle: { color: "#14532d", fontWeight: "800", fontSize: 17 },
  bannerText: { color: "#166534", fontSize: 13, marginTop: 3, lineHeight: 19 },
  whiteText: { color: "#ffffff" },
  errorBox: { backgroundColor: "#fff7ed", borderColor: "#fdba74", borderWidth: 1, padding: 12, borderRadius: 10, marginBottom: 15 },
  errorText: { color: "#9a3412" },
  alertCard: { backgroundColor: "#fff", borderLeftWidth: 5, borderLeftColor: "#dc2626", borderRadius: 14, padding: 18, marginBottom: 14 },
  alertLabel: { color: "#dc2626", fontWeight: "800", fontSize: 13 },
  alertTemp: { color: "#171717", fontWeight: "900", fontSize: 36, marginVertical: 7 },
  alertBody: { color: "#525252", fontSize: 13, lineHeight: 19, marginTop: 2 },
  sectionTitle: { fontSize: 17, fontWeight: "800", color: "#262626", marginTop: 10, marginBottom: 10 },
  spotCard: { backgroundColor: "#ffffff", borderRadius: 16, padding: 18, marginBottom: 12 },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  spotName: { fontSize: 19, fontWeight: "800", color: "#171717" },
  vehicle: { color: "#737373", marginTop: 3 },
  online: { color: "#16a34a", fontSize: 12, fontWeight: "700" },
  offline: { color: "#a3a3a3", fontSize: 12, fontWeight: "700" },
  metrics: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 18 },
  metric: { width: "47%", backgroundColor: "#f5f5f4", borderRadius: 12, padding: 13 },
  metricLabel: { color: "#737373", fontSize: 12 },
  metricValue: { color: "#171717", fontSize: 22, fontWeight: "800", marginTop: 3 },
  footer: { color: "#a3a3a3", fontSize: 11, textAlign: "center", lineHeight: 17, marginTop: 18 },
});
