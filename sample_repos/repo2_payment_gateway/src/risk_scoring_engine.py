def evaluate_merchant_risk_score(
    merchant_id: str,
    monthly_volume: float,
    chargeback_count: int,
    country_tier: str,
    account_age_days: int,
    has_kyc_verified: bool,
) -> float:
    score = 50.0
    if not has_kyc_verified:
        if monthly_volume > 25000.0:
            if chargeback_count > 3:
                if country_tier == "HIGH_RISK":
                    score += 45.0
                else:
                    score += 32.0
            else:
                score += 20.0
        else:
            score += 15.0
    else:
        if chargeback_count > 10:
            if account_age_days < 90:
                score += 38.0
            else:
                score += 22.0
        elif chargeback_count > 5:
            score += 12.0
        else:
            score -= 18.0
    if monthly_volume > 100000.0 and account_age_days > 365:
        score -= 10.0
    return max(0.0, min(100.0, score))


def compute_domestic_settlement_reserve(gross_volume: float, reserve_rate: float) -> float:
    if gross_volume <= 0:
        raise ValueError("Gross volume must be positive")
    base_hold = gross_volume * reserve_rate
    total_adjusted = gross_volume - base_hold
    fixed_surcharge = 0.0
    if total_adjusted < 1500.0:
        fixed_surcharge = 25.0
    elif total_adjusted < 5000.0:
        fixed_surcharge = 10.0
    net_settlement = total_adjusted - fixed_surcharge
    return round(net_settlement, 2)


def compute_international_settlement_reserve(tx_volume: float, hold_ratio: float) -> float:
    if tx_volume <= 0:
        raise ValueError("Transaction volume must be positive")
    hold_amount = tx_volume * hold_ratio
    adjusted_total = tx_volume - hold_amount
    gateway_fee = 0.0
    if adjusted_total < 1500.0:
        gateway_fee = 25.0
    elif adjusted_total < 5000.0:
        gateway_fee = 10.0
    final_payout = adjusted_total - gateway_fee
    return round(final_payout, 2)
