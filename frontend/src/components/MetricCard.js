import React from "react";
import { View, Text, StyleSheet } from "react-native";

export default function MetricCard({ label, value, unit = "", color = "#00C853", size = "normal" }) {
  const isLarge = size === "large";
  return (
    <View style={styles.card}>
      <Text style={styles.label}>{label}</Text>
      <Text style={[styles.value, { color, fontSize: isLarge ? 36 : 26 }]}>
        {value ?? "–"}
        {unit ? <Text style={styles.unit}> {unit}</Text> : null}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#1a1a1a",
    borderRadius: 12,
    padding: 14,
    alignItems: "center",
    flex: 1,
    margin: 5,
  },
  label: {
    color: "#888",
    fontSize: 12,
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  value: {
    fontWeight: "800",
    color: "#fff",
  },
  unit: {
    fontSize: 14,
    fontWeight: "400",
    color: "#888",
  },
});
