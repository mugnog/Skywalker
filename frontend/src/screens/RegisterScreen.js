import React, { useState } from "react";
import {
  View, Text, StyleSheet, TextInput,
  TouchableOpacity, ActivityIndicator, KeyboardAvoidingView,
  Platform, ScrollView,
} from "react-native";
import { register } from "../services/auth";

export default function RegisterScreen({ onLogin, onGoLogin }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [ftp, setFtp] = useState("230");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleRegister = async () => {
    if (!email || !password || !name) { setError("Bitte alle Felder ausfüllen."); return; }
    setLoading(true);
    setError(null);
    try {
      const user = await register({ email, password, name, ftp_override: parseInt(ftp) || 230 });
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
        <Text style={styles.title}>Registrieren</Text>
        <Text style={styles.subtitle}>Erstelle deinen Skywalker Account</Text>

        <View style={styles.form}>
          <TextInput style={styles.input} placeholder="Dein Name" placeholderTextColor="#555" value={name} onChangeText={setName} />
          <TextInput style={styles.input} placeholder="E-Mail" placeholderTextColor="#555" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
          <TextInput style={styles.input} placeholder="Passwort" placeholderTextColor="#555" value={password} onChangeText={setPassword} secureTextEntry />
          <View style={styles.ftpRow}>
            <Text style={styles.ftpLabel}>Mein FTP (Watt)</Text>
            <TextInput
              style={[styles.input, styles.ftpInput]}
              placeholder="230"
              placeholderTextColor="#555"
              value={ftp}
              onChangeText={setFtp}
              keyboardType="numeric"
            />
          </View>
          <Text style={styles.ftpHint}>Du kannst das später noch ändern.</Text>

          {error && <Text style={styles.error}>{error}</Text>}

          <TouchableOpacity style={styles.btn} onPress={handleRegister} disabled={loading}>
            {loading
              ? <ActivityIndicator color="#000" />
              : <Text style={styles.btnText}>Account erstellen</Text>
            }
          </TouchableOpacity>

          <TouchableOpacity style={styles.linkBtn} onPress={onGoLogin}>
            <Text style={styles.linkText}>Schon registriert? Einloggen →</Text>
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
  title: { color: "#00C853", fontSize: 28, fontWeight: "900" },
  subtitle: { color: "#555", fontSize: 13, marginBottom: 40 },
  form: { width: "100%" },
  input: { backgroundColor: "#1a1a1a", borderRadius: 12, padding: 16, color: "#fff", fontSize: 15, marginBottom: 12, borderWidth: 1, borderColor: "#333" },
  ftpRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  ftpLabel: { color: "#ccc", fontSize: 14, flex: 1 },
  ftpInput: { flex: 0, width: 80, textAlign: "center" },
  ftpHint: { color: "#444", fontSize: 11, marginBottom: 16, marginTop: -6 },
  error: { color: "#FF1744", marginBottom: 12, textAlign: "center" },
  btn: { backgroundColor: "#00C853", borderRadius: 12, padding: 16, alignItems: "center", marginBottom: 16 },
  btnText: { color: "#000", fontWeight: "800", fontSize: 16 },
  linkBtn: { alignItems: "center" },
  linkText: { color: "#555", fontSize: 13 },
});
