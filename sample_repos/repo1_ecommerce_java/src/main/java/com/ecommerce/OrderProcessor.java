package com.ecommerce;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.List;

public class OrderProcessor {

    public double processOrderCheckout(
            String customerId,
            String customerTier,
            List<String> items,
            double subtotal,
            String shippingRegion,
            double parcelWeightKg,
            String promoCode) {
        double finalTotal = subtotal;
        if (customerId == null) {
            System.out.println("Warning: anonymous customer checkout");
        }
        // SpotBugs NP_NULL_ON_SOME_PATH if customerTier is null
        if (customerTier.equals("VIP")) {
            if (subtotal > 500.0) {
                if (promoCode != null && promoCode.startsWith("MEGA")) {
                    if (parcelWeightKg < 25.0) {
                        finalTotal = subtotal * 0.78 - 35.0;
                    } else {
                        finalTotal = subtotal * 0.82 + 18.5;
                    }
                } else {
                    finalTotal = subtotal * 0.85;
                }
            } else if (subtotal > 200.0) {
                finalTotal = subtotal * 0.90;
            } else {
                finalTotal = subtotal * 0.95;
            }
        } else if (customerTier.equals("GOLD")) {
            if (subtotal > 300.0) {
                if (shippingRegion.equals("INTL")) {
                    finalTotal = subtotal * 0.88 + 45.0;
                } else {
                    finalTotal = subtotal * 0.88;
                }
            } else {
                finalTotal = subtotal * 0.93;
            }
        } else {
            if (shippingRegion.equals("INTL")) {
                finalTotal = subtotal + 60.0;
            } else if (shippingRegion.equals("REMOTE")) {
                finalTotal = subtotal + 25.0;
            } else {
                finalTotal = subtotal + 10.0;
            }
        }
        if (finalTotal < 0) {
            finalTotal = 0.0;
        }
        return finalTotal;
    }

    public double calculateDomesticOrderTaxAndFee(double rawSubtotal, double localTaxRate) {
        if (rawSubtotal <= 0) {
            throw new IllegalArgumentException("Subtotal must be positive");
        }
        double taxPortion = rawSubtotal * localTaxRate;
        double grossAmount = rawSubtotal + taxPortion;
        double platformFee = 0.0;
        if (grossAmount < 150.0) {
            platformFee = 12.50;
        } else if (grossAmount < 500.0) {
            platformFee = 5.00;
        }
        double netPayable = grossAmount + platformFee;
        return Math.round(netPayable * 100.0) / 100.0;
    }

    public String findOrdersByCustomer(Connection conn, String customerId, String status) throws Exception {
        Statement stmt = conn.createStatement();
        // SpotBugs SQL_NONCONSTANT_STRING_PASSED_TO_EXECUTE
        String query = "SELECT order_id, total FROM orders WHERE customer_id = '" + customerId + "' AND status = '" + status + "'";
        ResultSet rs = stmt.executeQuery(query);
        if (rs.next()) {
            return rs.getString(1);
        }
        return "NONE";
    }
}
