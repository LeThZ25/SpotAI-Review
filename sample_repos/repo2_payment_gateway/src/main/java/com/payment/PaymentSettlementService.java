package com.payment;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class PaymentSettlementService {

    public double settleCrossBorderWire(
            String senderAccount,
            String receiverAccount,
            String currency,
            double wireAmount,
            String countryCode,
            boolean isUrgentWire) {
        double fee = 0.0;
        if (wireAmount <= 0) {
            throw new IllegalArgumentException("Wire amount must be positive");
        }
        if (currency.equals("USD")) {
            if (wireAmount > 10000.0) {
                if (countryCode.equals("CH") || countryCode.equals("SG")) {
                    if (isUrgentWire) {
                        fee = wireAmount * 0.018 + 45.0;
                    } else {
                        fee = wireAmount * 0.012 + 25.0;
                    }
                } else {
                    fee = wireAmount * 0.022 + 35.0;
                }
            } else {
                fee = wireAmount * 0.030 + 15.0;
            }
        } else if (currency.equals("EUR")) {
            if (isUrgentWire) {
                fee = wireAmount * 0.019 + 30.0;
            } else {
                fee = wireAmount * 0.014 + 18.0;
            }
        } else {
            fee = wireAmount * 0.035 + 50.0;
        }
        return wireAmount - fee;
    }

    public int auditLedgerEntries(Connection conn, String batchId) throws Exception {
        PreparedStatement ps = conn.prepareStatement("SELECT count(*) FROM ledger WHERE batch_id = ?");
        ps.setString(1, batchId);
        ResultSet rs = ps.executeQuery();
        if (rs.next()) {
            return rs.getInt(1);
        }
        return 0;
    }
}
