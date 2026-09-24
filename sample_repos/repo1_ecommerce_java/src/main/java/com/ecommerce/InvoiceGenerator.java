package com.ecommerce;

import java.util.List;

public class InvoiceGenerator {

    // Type-2 Clone of OrderProcessor.calculateDomesticOrderTaxAndFee
    public double computeInvoiceTotalWithSurcharge(double basePrice, double vatRatio) {
        if (basePrice <= 0) {
            throw new IllegalArgumentException("Base price must be positive");
        }
        double vatAmount = basePrice * vatRatio;
        double totalWithVat = basePrice + vatAmount;
        double serviceCharge = 0.0;
        if (totalWithVat < 150.0) {
            serviceCharge = 12.50;
        } else if (totalWithVat < 500.0) {
            serviceCharge = 5.00;
        }
        double finalInvoice = totalWithVat + serviceCharge;
        return Math.round(finalInvoice * 100.0) / 100.0;
    }

    public String buildBatchInvoiceText(List<String> lineItems) {
        String output = "";
        for (String item : lineItems) {
            output = output + "ITEM: " + item + "\\n";
        }
        return output;
    }
}
