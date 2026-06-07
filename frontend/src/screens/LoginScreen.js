import React, { useState } from "react";
import {
  View, Text, StyleSheet, TextInput,
  TouchableOpacity, ActivityIndicator, KeyboardAvoidingView,
  Platform, ScrollView,
} from "react-native";
import { login } from "../services/auth";

export default function LoginScreen({ onLogin, onGoRegister }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleLogin = async () => {
    if (!email || !password) { setError("Bitte E-Mail und Passwort eingeben."); return; }
    setLoading(true);
    setError(null);
    try {
      const user = await login({ email, password });
      onLogin(user);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.inner}>
        <Text style={styles.logo}>⚡</Text>
        <Text style={styles.title}>SKYWALKER</Text>
        <Text style={styles.subtitle}>AI Cycling Coach</Text>

        <View style={styles.form}>
          <TextInput
            style={styles.input}
            placeholder="E-Mail"
            placeholderTextColor="#555"
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
          />
          <TextInput
            style={styles.input}
            placeholder="Passwort"
            placeholderTextColor="#555"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
          />

          {error && <Text style={styles.error}>{error}</Text>}

          <TouchableOpacity style={styles.btn} onPress={handleLogin} disabled={loading}>
            {loading
              ? <ActivityIndicator color="#000" />
              : <Text style={styles.btnText}>Einloggen</Text>
            }
          </TouchableOpacity>

          <TouchableOpacity style={styles.linkBtn} onPress={onGoRegister}>
            <Text style={styles.linkText}>Noch kein Account? Jetzt registrieren →</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#111" },
  inner: { flexGrow: 1, justifyContent: "center", alignItems: "center", padding: 30 },
  logo: { fontSize: 60, marginBottom: 10 },
  title: { color: "#00C853", fontSize: 32, fontWeight: "900", letterSpacing: 3 },
  subtitle: { color: "#555", fontSize: 14, marginBottom: 50 },
  form: { width: "100%" },
  input: { backgroundColor: "#1a1a1a", borderRadius: 12, padding: 16, color: "#fff", fontSize: 15, marginBottom: 12, borderWidth: 1, borderColor: "#333" },
  error: { color: "#FF1744", marginBottom: 12, textAlign: "center" },
  btn: { backgroundColor: "#00C853", borderRadius: 12, padding: 16, alignItems: "center", marginBottom: 16 },
  btnText: { color: "#000", fontWeight: "800", fontSize: 16 },
  linkBtn: { alignItems: "center" },
  linkText: { color: "#555", fontSize: 13 },
});
