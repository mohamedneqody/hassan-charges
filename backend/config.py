"""
Hassan Charges - Configuration
All currency pairs with realistic base prices and metadata.
"""

import os
from dotenv import load_dotenv

load_dotenv()

TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# All currency pairs organized by category
FOREX_PAIRS = {
    # ═══════════════════ MAJOR PAIRS ═══════════════════
    "EUR/USD": {"price": 1.0845, "cat": "major", "bf": "🇪🇺", "qf": "🇺🇸", "d": 4},
    "GBP/USD": {"price": 1.2715, "cat": "major", "bf": "🇬🇧", "qf": "🇺🇸", "d": 4},
    "USD/JPY": {"price": 154.50, "cat": "major", "bf": "🇺🇸", "qf": "🇯🇵", "d": 2},
    "USD/CHF": {"price": 0.8835, "cat": "major", "bf": "🇺🇸", "qf": "🇨🇭", "d": 4},
    "AUD/USD": {"price": 0.6520, "cat": "major", "bf": "🇦🇺", "qf": "🇺🇸", "d": 4},
    "USD/CAD": {"price": 1.3680, "cat": "major", "bf": "🇺🇸", "qf": "🇨🇦", "d": 4},
    "NZD/USD": {"price": 0.5985, "cat": "major", "bf": "🇳🇿", "qf": "🇺🇸", "d": 4},

    # ═══════════════════ MINOR / CROSS PAIRS ═══════════════════
    "EUR/GBP": {"price": 0.8530, "cat": "minor", "bf": "🇪🇺", "qf": "🇬🇧", "d": 4},
    "EUR/JPY": {"price": 167.55, "cat": "minor", "bf": "🇪🇺", "qf": "🇯🇵", "d": 2},
    "EUR/CHF": {"price": 0.9580, "cat": "minor", "bf": "🇪🇺", "qf": "🇨🇭", "d": 4},
    "EUR/AUD": {"price": 1.6635, "cat": "minor", "bf": "🇪🇺", "qf": "🇦🇺", "d": 4},
    "EUR/CAD": {"price": 1.4830, "cat": "minor", "bf": "🇪🇺", "qf": "🇨🇦", "d": 4},
    "EUR/NZD": {"price": 1.8120, "cat": "minor", "bf": "🇪🇺", "qf": "🇳🇿", "d": 4},
    "GBP/JPY": {"price": 196.45, "cat": "minor", "bf": "🇬🇧", "qf": "🇯🇵", "d": 2},
    "GBP/CHF": {"price": 1.1230, "cat": "minor", "bf": "🇬🇧", "qf": "🇨🇭", "d": 4},
    "GBP/AUD": {"price": 1.9505, "cat": "minor", "bf": "🇬🇧", "qf": "🇦🇺", "d": 4},
    "GBP/CAD": {"price": 1.7390, "cat": "minor", "bf": "🇬🇧", "qf": "🇨🇦", "d": 4},
    "GBP/NZD": {"price": 2.1240, "cat": "minor", "bf": "🇬🇧", "qf": "🇳🇿", "d": 4},
    "AUD/JPY": {"price": 100.70, "cat": "minor", "bf": "🇦🇺", "qf": "🇯🇵", "d": 2},
    "AUD/CHF": {"price": 0.5760, "cat": "minor", "bf": "🇦🇺", "qf": "🇨🇭", "d": 4},
    "AUD/CAD": {"price": 0.8920, "cat": "minor", "bf": "🇦🇺", "qf": "🇨🇦", "d": 4},
    "AUD/NZD": {"price": 1.0890, "cat": "minor", "bf": "🇦🇺", "qf": "🇳🇿", "d": 4},
    "NZD/JPY": {"price": 92.45, "cat": "minor", "bf": "🇳🇿", "qf": "🇯🇵", "d": 2},
    "NZD/CHF": {"price": 0.5290, "cat": "minor", "bf": "🇳🇿", "qf": "🇨🇭", "d": 4},
    "NZD/CAD": {"price": 0.8190, "cat": "minor", "bf": "🇳🇿", "qf": "🇨🇦", "d": 4},
    "CHF/JPY": {"price": 174.90, "cat": "minor", "bf": "🇨🇭", "qf": "🇯🇵", "d": 2},
    "CAD/JPY": {"price": 112.90, "cat": "minor", "bf": "🇨🇦", "qf": "🇯🇵", "d": 2},
    "CAD/CHF": {"price": 0.6460, "cat": "minor", "bf": "🇨🇦", "qf": "🇨🇭", "d": 4},

    # ═══════════════════ EXOTIC PAIRS ═══════════════════
    "USD/EGP": {"price": 50.50, "cat": "exotic", "bf": "🇺🇸", "qf": "🇪🇬", "d": 2},
    "USD/SAR": {"price": 3.7500, "cat": "exotic", "bf": "🇺🇸", "qf": "🇸🇦", "d": 4},
    "USD/AED": {"price": 3.6730, "cat": "exotic", "bf": "🇺🇸", "qf": "🇦🇪", "d": 4},
    "USD/TRY": {"price": 38.50, "cat": "exotic", "bf": "🇺🇸", "qf": "🇹🇷", "d": 2},
    "USD/ZAR": {"price": 18.35, "cat": "exotic", "bf": "🇺🇸", "qf": "🇿🇦", "d": 4},
    "USD/MXN": {"price": 17.15, "cat": "exotic", "bf": "🇺🇸", "qf": "🇲🇽", "d": 4},
    "USD/SGD": {"price": 1.3480, "cat": "exotic", "bf": "🇺🇸", "qf": "🇸🇬", "d": 4},
    "USD/HKD": {"price": 7.8120, "cat": "exotic", "bf": "🇺🇸", "qf": "🇭🇰", "d": 4},
    "USD/THB": {"price": 35.80, "cat": "exotic", "bf": "🇺🇸", "qf": "🇹🇭", "d": 2},
    "USD/INR": {"price": 83.45, "cat": "exotic", "bf": "🇺🇸", "qf": "🇮🇳", "d": 2},
    "USD/BRL": {"price": 5.0500, "cat": "exotic", "bf": "🇺🇸", "qf": "🇧🇷", "d": 4},
    "USD/PLN": {"price": 4.0200, "cat": "exotic", "bf": "🇺🇸", "qf": "🇵🇱", "d": 4},
    "USD/NOK": {"price": 10.85, "cat": "exotic", "bf": "🇺🇸", "qf": "🇳🇴", "d": 4},
    "USD/SEK": {"price": 10.52, "cat": "exotic", "bf": "🇺🇸", "qf": "🇸🇪", "d": 4},
    "USD/DKK": {"price": 6.8800, "cat": "exotic", "bf": "🇺🇸", "qf": "🇩🇰", "d": 4},
    "USD/CZK": {"price": 23.15, "cat": "exotic", "bf": "🇺🇸", "qf": "🇨🇿", "d": 2},
    "USD/HUF": {"price": 365.50, "cat": "exotic", "bf": "🇺🇸", "qf": "🇭🇺", "d": 2},
    "USD/ILS": {"price": 3.6500, "cat": "exotic", "bf": "🇺🇸", "qf": "🇮🇱", "d": 4},
    "USD/KWD": {"price": 0.3080, "cat": "exotic", "bf": "🇺🇸", "qf": "🇰🇼", "d": 4},
    "USD/QAR": {"price": 3.6400, "cat": "exotic", "bf": "🇺🇸", "qf": "🇶🇦", "d": 4},
    "USD/BHD": {"price": 0.3770, "cat": "exotic", "bf": "🇺🇸", "qf": "🇧🇭", "d": 4},
    "USD/OMR": {"price": 0.3845, "cat": "exotic", "bf": "🇺🇸", "qf": "🇴🇲", "d": 4},
    "USD/JOD": {"price": 0.7090, "cat": "exotic", "bf": "🇺🇸", "qf": "🇯🇴", "d": 4},
    "USD/CNY": {"price": 7.2450, "cat": "exotic", "bf": "🇺🇸", "qf": "🇨🇳", "d": 4},
    "USD/KRW": {"price": 1345.0, "cat": "exotic", "bf": "🇺🇸", "qf": "🇰🇷", "d": 2},
    "USD/PHP": {"price": 56.80, "cat": "exotic", "bf": "🇺🇸", "qf": "🇵🇭", "d": 2},
    "USD/IDR": {"price": 15850.0, "cat": "exotic", "bf": "🇺🇸", "qf": "🇮🇩", "d": 0},
    "USD/MYR": {"price": 4.7200, "cat": "exotic", "bf": "🇺🇸", "qf": "🇲🇾", "d": 4},
    "USD/PKR": {"price": 278.50, "cat": "exotic", "bf": "🇺🇸", "qf": "🇵🇰", "d": 2},
    "USD/NGN": {"price": 1550.0, "cat": "exotic", "bf": "🇺🇸", "qf": "🇳🇬", "d": 2},
    "USD/KES": {"price": 152.50, "cat": "exotic", "bf": "🇺🇸", "qf": "🇰🇪", "d": 2},
    "USD/MAD": {"price": 10.05, "cat": "exotic", "bf": "🇺🇸", "qf": "🇲🇦", "d": 4},
    "USD/TWD": {"price": 32.15, "cat": "exotic", "bf": "🇺🇸", "qf": "🇹🇼", "d": 2},
    "USD/VND": {"price": 25400.0, "cat": "exotic", "bf": "🇺🇸", "qf": "🇻🇳", "d": 0},
    "USD/LKR": {"price": 298.00, "cat": "exotic", "bf": "🇺🇸", "qf": "🇱🇰", "d": 2},
    "USD/GHS": {"price": 14.80, "cat": "exotic", "bf": "🇺🇸", "qf": "🇬🇭", "d": 2},
    "USD/COP": {"price": 3950.0, "cat": "exotic", "bf": "🇺🇸", "qf": "🇨🇴", "d": 2},
    "USD/ARS": {"price": 890.00, "cat": "exotic", "bf": "🇺🇸", "qf": "🇦🇷", "d": 2},
    "USD/CLP": {"price": 950.00, "cat": "exotic", "bf": "🇺🇸", "qf": "🇨🇱", "d": 2},
    "USD/PEN": {"price": 3.7500, "cat": "exotic", "bf": "🇺🇸", "qf": "🇵🇪", "d": 4},
    "USD/UYU": {"price": 38.20, "cat": "exotic", "bf": "🇺🇸", "qf": "🇺🇾", "d": 2},
    "USD/DZD": {"price": 134.50, "cat": "exotic", "bf": "🇺🇸", "qf": "🇩🇿", "d": 2},
    "USD/TND": {"price": 3.1200, "cat": "exotic", "bf": "🇺🇸", "qf": "🇹🇳", "d": 4},
    "EUR/TRY": {"price": 41.75, "cat": "exotic", "bf": "🇪🇺", "qf": "🇹🇷", "d": 2},
    "GBP/TRY": {"price": 48.95, "cat": "exotic", "bf": "🇬🇧", "qf": "🇹🇷", "d": 2},

    # ═══════════════════ CRYPTO ═══════════════════
    "BTC/USD": {"price": 67500.0, "cat": "crypto", "bf": "₿", "qf": "🇺🇸", "d": 2},
    "ETH/USD": {"price": 3250.0, "cat": "crypto", "bf": "Ξ", "qf": "🇺🇸", "d": 2},
    "XRP/USD": {"price": 0.5520, "cat": "crypto", "bf": "✕", "qf": "🇺🇸", "d": 4},
    "SOL/USD": {"price": 145.80, "cat": "crypto", "bf": "◎", "qf": "🇺🇸", "d": 2},
    "ADA/USD": {"price": 0.4580, "cat": "crypto", "bf": "₳", "qf": "🇺🇸", "d": 4},
    "DOGE/USD": {"price": 0.1650, "cat": "crypto", "bf": "Ð", "qf": "🇺🇸", "d": 4},
    "BNB/USD": {"price": 580.00, "cat": "crypto", "bf": "◆", "qf": "🇺🇸", "d": 2},
    "AVAX/USD": {"price": 35.40, "cat": "crypto", "bf": "▲", "qf": "🇺🇸", "d": 2},
    "LINK/USD": {"price": 18.50, "cat": "crypto", "bf": "🔗", "qf": "🇺🇸", "d": 2},
    "DOT/USD": {"price": 7.20, "cat": "crypto", "bf": "●", "qf": "🇺🇸", "d": 2},
    "MATIC/USD": {"price": 0.75, "cat": "crypto", "bf": "⬡", "qf": "🇺🇸", "d": 4},
    "SHIB/USD": {"price": 0.000025, "cat": "crypto", "bf": "🐕", "qf": "🇺🇸", "d": 6},
    "LTC/USD": {"price": 85.00, "cat": "crypto", "bf": "Ł", "qf": "🇺🇸", "d": 2},
    "UNI/USD": {"price": 7.80, "cat": "crypto", "bf": "🦄", "qf": "🇺🇸", "d": 2},
}

CURRENCY_NAMES = {
    "USD": "US Dollar", "EUR": "Euro", "GBP": "British Pound", "JPY": "Japanese Yen",
    "CHF": "Swiss Franc", "AUD": "Australian Dollar", "CAD": "Canadian Dollar",
    "NZD": "New Zealand Dollar", "EGP": "Egyptian Pound", "SAR": "Saudi Riyal",
    "AED": "UAE Dirham", "TRY": "Turkish Lira", "ZAR": "South African Rand",
    "MXN": "Mexican Peso", "SGD": "Singapore Dollar", "HKD": "Hong Kong Dollar",
    "THB": "Thai Baht", "INR": "Indian Rupee", "BRL": "Brazilian Real",
    "PLN": "Polish Zloty", "NOK": "Norwegian Krone", "SEK": "Swedish Krona",
    "DKK": "Danish Krone", "CZK": "Czech Koruna", "HUF": "Hungarian Forint",
    "ILS": "Israeli Shekel", "KWD": "Kuwaiti Dinar", "QAR": "Qatari Riyal",
    "BHD": "Bahraini Dinar", "OMR": "Omani Rial", "JOD": "Jordanian Dinar",
    "CNY": "Chinese Yuan", "KRW": "Korean Won", "PHP": "Philippine Peso",
    "IDR": "Indonesian Rupiah", "MYR": "Malaysian Ringgit", "PKR": "Pakistani Rupee",
    "NGN": "Nigerian Naira", "KES": "Kenyan Shilling", "MAD": "Moroccan Dirham",
    "TWD": "Taiwan Dollar", "VND": "Vietnamese Dong", "LKR": "Sri Lankan Rupee",
    "GHS": "Ghanaian Cedi", "COP": "Colombian Peso", "ARS": "Argentine Peso",
    "CLP": "Chilean Peso", "PEN": "Peruvian Sol", "UYU": "Uruguayan Peso",
    "DZD": "Algerian Dinar", "TND": "Tunisian Dinar",
    "BTC": "Bitcoin", "ETH": "Ethereum", "XRP": "Ripple", "SOL": "Solana",
    "ADA": "Cardano", "DOGE": "Dogecoin", "BNB": "BNB", "AVAX": "Avalanche",
    "LINK": "Chainlink", "DOT": "Polkadot", "MATIC": "Polygon", "SHIB": "Shiba Inu",
    "LTC": "Litecoin", "UNI": "Uniswap",
}
