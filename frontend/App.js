import React, { useEffect, useState } from "react";
import { View, ActivityIndicator } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { Text } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import HomeScreen from "./src/screens/HomeScreen";
import CheckinScreen from "./src/screens/CheckinScreen";
import CoachScreen from "./src/screens/CoachScreen";
import ActivitiesScreen from "./src/screens/ActivitiesScreen";
import TrendsScreen from "./src/screens/TrendsScreen";
import LoginScreen from "./src/screens/LoginScreen";
import RegisterScreen from "./src/screens/RegisterScreen";
import SettingsScreen from "./src/screens/SettingsScreen";
import GoalsScreen from "./src/screens/GoalsScreen";

import { isLoggedIn, logout, getUser } from "./src/services/auth";
import { api, setUnauthorizedHandler } from "./src/services/api";

const Tab = createBottomTabNavigator();

const ICONS = {
  Home: "⚡",
  "Check-in": "☀️",
  Coach: "🤖",
  "Aktivitäten": "🚴",
  Trends: "📈",
  Einstellungen: "⚙️",
};

export default function App() {
  const [authState, setAuthState] = useState("loading"); // loading | login | register | app
  const [user, setUser] = useState(null);
  const [checkinDone, setCheckinDone] = useState(false);

  const refreshCheckinStatus = () => {
    api.checkinToday().then((d) => setCheckinDone(!!d?.exists)).catch(() => {});
  };

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setAuthState("login");
    });
  }, []);

  useEffect(() => {
    isLoggedIn().then((loggedIn) => {
      if (loggedIn) {
        getUser().then((u) => { setUser(u); setAuthState("app"); });
        refreshCheckinStatus();
      } else {
        setAuthState("login");
      }
    });
  }, []);

  const handleLogin = (userData) => {
    setUser(userData);
    // Kein FTP-Ziel gesetzt → Goals-Screen zeigen
    if (!userData.ftp_target || userData.ftp_target === 0) {
      setAuthState("goals");
    } else {
      setAuthState("app");
    }
  };

  const handleGoalsDone = (ftpTarget) => {
    if (ftpTarget) {
      setUser((prev) => ({ ...prev, ftp_target: ftpTarget }));
    }
    setAuthState("app");
  };

  const handleLogout = async () => {
    await logout();
    setUser(null);
    setAuthState("login");
  };

  if (authState === "loading") {
    return (
      <View style={{ flex: 1, backgroundColor: "#111", justifyContent: "center", alignItems: "center" }}>
        <Text style={{ fontSize: 40, marginBottom: 20 }}>⚡</Text>
        <ActivityIndicator color="#00C853" size="large" />
      </View>
    );
  }

  if (authState === "login") {
    return (
      <GestureHandlerRootView style={{ flex: 1 }}>
        <LoginScreen onLogin={handleLogin} onGoRegister={() => setAuthState("register")} />
      </GestureHandlerRootView>
    );
  }

  if (authState === "register") {
    return (
      <GestureHandlerRootView style={{ flex: 1 }}>
        <RegisterScreen onLogin={handleLogin} onGoLogin={() => setAuthState("login")} />
      </GestureHandlerRootView>
    );
  }

  if (authState === "goals") {
    return (
      <GestureHandlerRootView style={{ flex: 1 }}>
        <GoalsScreen onDone={handleGoalsDone} />
      </GestureHandlerRootView>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <NavigationContainer>
        <Tab.Navigator
          screenOptions={({ route }) => ({
            headerShown: false,
            tabBarStyle: { backgroundColor: "#111", borderTopColor: "#222", height: 80, paddingBottom: 12 },
            tabBarActiveTintColor: "#00C853",
            tabBarInactiveTintColor: "#444",
            tabBarLabelStyle: { fontSize: 11, fontWeight: "700" },
            tabBarIcon: ({ color, size }) => (
              <Text style={{ fontSize: size - 4, color }}>{ICONS[route.name]}</Text>
            ),
          })}
        >
          <Tab.Screen name="Home">
            {() => <HomeScreen user={user} onLogout={handleLogout} />}
          </Tab.Screen>
          <Tab.Screen
            name="Check-in"
            options={{ tabBarBadge: checkinDone ? undefined : "!" }}
          >
            {() => <CheckinScreen onCheckinSaved={() => setCheckinDone(true)} />}
          </Tab.Screen>
          <Tab.Screen name="Coach" component={CoachScreen} />
          <Tab.Screen name="Aktivitäten" component={ActivitiesScreen} />
          <Tab.Screen name="Trends" component={TrendsScreen} />
          <Tab.Screen name="Einstellungen">
            {() => <SettingsScreen user={user} onLogout={handleLogout} />}
          </Tab.Screen>
        </Tab.Navigator>
      </NavigationContainer>
    </GestureHandlerRootView>
  );
}
