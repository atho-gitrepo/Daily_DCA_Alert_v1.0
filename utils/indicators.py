"""
Technical Indicators for DCA Day Trading
Includes Super TDI + Bollinger Bands + Heikin-Ashi
Version: 1.0.0
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Heikin-Ashi candles from OHLC data.
    Returns DataFrame with additional HA columns.
    """
    if df.empty or len(df) < 2:
        return df

    ha_df = df.copy()

    # Heikin-Ashi formulas
    ha_df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    ha_df['ha_open'] = (df['open'].shift(1) + df['close'].shift(1)) / 2
    ha_df['ha_high'] = df[['high', 'ha_open', 'ha_close']].max(axis=1)
    ha_df['ha_low'] = df[['low', 'ha_open', 'ha_close']].min(axis=1)

    # Fill first row's HA open with regular open
    ha_df.loc[ha_df.index[0], 'ha_open'] = df.loc[df.index[0], 'open']

    # Determine HA color: 1 = bullish, -1 = bearish
    ha_df['ha_color'] = np.where(
        ha_df['ha_close'] >= ha_df['ha_open'], 1, -1
    )

    # HA body size and wick sizes
    ha_df['ha_body'] = abs(ha_df['ha_close'] - ha_df['ha_open'])
    ha_df['ha_upper_wick'] = ha_df['ha_high'] - ha_df[['ha_open', 'ha_close']].max(axis=1)
    ha_df['ha_lower_wick'] = ha_df[['ha_open', 'ha_close']].min(axis=1) - ha_df['ha_low']

    return ha_df


class Indicators:
    """
    Technical indicator calculations for DCA strategy.
    """

    @staticmethod
    def calculate_tdi(df: pd.DataFrame, slow_period: int = 34,
                      fast_period: int = 13, signal_period: int = 34) -> pd.DataFrame:
        """
        Calculate Super TDI (Trade Dynamic Index).

        Super TDI Components:
        - RSI-based moving averages
        - Volatility bands
        - Signal line

        Returns DataFrame with TDI columns.
        """
        if df.empty or len(df) < max(slow_period, fast_period, signal_period) + 1:
            return df

        result = df.copy()

        try:
            # 1. Calculate RSI
            rsi_period = 13
            delta = result['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
            rs = gain / loss
            result['tdi_rsi'] = 100 - (100 / (1 + rs))

            # 2. RSI-based Moving Averages
            # TDI Fast MA (usually 13-period MA of RSI)
            result['tdi_fast_ma'] = result['tdi_rsi'].rolling(window=fast_period).mean()

            # TDI Slow MA (usually 34-period MA of RSI)
            result['tdi_slow_ma'] = result['tdi_rsi'].rolling(window=slow_period).mean()

            # 3. Volatility Bands (Standard Deviation-based)
            # Similar to Bollinger Bands on RSI
            tdi_std = result['tdi_rsi'].rolling(window=signal_period).std()
            result['tdi_upper_band'] = result['tdi_slow_ma'] + (2.0 * tdi_std)
            result['tdi_lower_band'] = result['tdi_slow_ma'] - (2.0 * tdi_std)

            # 4. TDI Signal (Market Baseline)
            # Typically a smoothed version of the slow MA
            result['tdi_signal'] = result['tdi_slow_ma'].rolling(window=7).mean()

            # 5. TDI Crossover Signals
            result['tdi_cross_fast'] = np.where(
                result['tdi_fast_ma'] > result['tdi_slow_ma'], 1,
                np.where(result['tdi_fast_ma'] < result['tdi_slow_ma'], -1, 0)
            )

            # 6. TDI Zone (0-100 scaling)
            result['tdi_zone'] = result['tdi_slow_ma']

            # 7. TDI Strength (momentum)
            result['tdi_momentum'] = result['tdi_rsi'] - result['tdi_slow_ma']

            # 8. TDI Trend Score
            result['tdi_trend_score'] = (
                (result['tdi_fast_ma'] > result['tdi_slow_ma']).astype(int) * 2 +
                (result['tdi_rsi'] > 50).astype(int) * 1
            )

            # 9. TDI Signal Strength
            result['tdi_signal_strength'] = abs(result['tdi_momentum']) / 50

        except Exception as e:
            logger.error(f"Error calculating TDI: {e}")

        return result

    @staticmethod
    def calculate_bollinger_bands(df: pd.DataFrame, period: int = 34,
                                  dev: float = 1.750) -> pd.DataFrame:
        """
        Calculate Bollinger Bands with standard deviation.

        Parameters:
        - period: Moving average period (default 34)
        - dev: Number of standard deviations (default 1.750)
        """
        if df.empty or len(df) < period + 1:
            return df

        result = df.copy()

        try:
            # Calculate moving average
            result['bb_ma'] = result['close'].rolling(window=period).mean()

            # Calculate standard deviation
            result['bb_std'] = result['close'].rolling(window=period).std()

            # Calculate upper and lower bands
            result['bb_upper'] = result['bb_ma'] + (dev * result['bb_std'])
            result['bb_lower'] = result['bb_ma'] - (dev * result['bb_std'])

            # Calculate bandwidth
            result['bb_width'] = result['bb_upper'] - result['bb_lower']
            result['bb_width_percent'] = result['bb_width'] / result['bb_ma']

            # Calculate position within bands (0 to 1)
            result['bb_position'] = (result['close'] - result['bb_lower']) / result['bb_width']

            # Band squeeze detection
            result['bb_squeeze'] = result['bb_width_percent'] < result['bb_width_percent'].rolling(20).mean()

            # Bollinger Band %B (0 = lower, 1 = upper)
            result['bb_percent_b'] = (result['close'] - result['bb_lower']) / (result['bb_upper'] - result['bb_lower'])

            # Band width ratio
            result['bb_width_ratio'] = result['bb_width'] / result['bb_width'].rolling(50).mean()

        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {e}")

        return result

    @staticmethod
    def calculate_volume_profile(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """
        Calculate volume-based indicators.
        """
        if df.empty:
            return df

        result = df.copy()

        try:
            # Volume moving average
            result['volume_ma'] = result['volume'].rolling(window=period).mean()

            # Volume ratio (current / average)
            result['volume_ratio'] = result['volume'] / result['volume_ma']

            # Volume spike detection
            result['volume_spike'] = result['volume_ratio'] > 1.5

            # Volume Weighted Average Price (VWAP)
            result['vwap'] = (result['volume'] * (result['high'] + result['low'] + result['close']) / 3).cumsum() / result['volume'].cumsum()

            # Volume profile - price levels with high volume
            result['volume_high'] = result['volume'].rolling(window=10).max()
            result['volume_low'] = result['volume'].rolling(window=10).min()

        except Exception as e:
            logger.error(f"Error calculating volume profile: {e}")

        return result

    @staticmethod
    def calculate_momentum_oscillators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate momentum oscillators for entry confirmation.
        """
        if df.empty or len(df) < 14:
            return df

        result = df.copy()

        try:
            # MACD
            exp1 = result['close'].ewm(span=12, adjust=False).mean()
            exp2 = result['close'].ewm(span=26, adjust=False).mean()
            result['macd'] = exp1 - exp2
            result['macd_signal'] = result['macd'].ewm(span=9, adjust=False).mean()
            result['macd_histogram'] = result['macd'] - result['macd_signal']

            # RSI (standard)
            delta = result['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            result['rsi'] = 100 - (100 / (1 + rs))

            # Stochastic Oscillator
            low_14 = result['low'].rolling(window=14).min()
            high_14 = result['high'].rolling(window=14).max()
            result['stoch_k'] = 100 * ((result['close'] - low_14) / (high_14 - low_14))
            result['stoch_d'] = result['stoch_k'].rolling(window=3).mean()

        except Exception as e:
            logger.error(f"Error calculating momentum oscillators: {e}")

        return result

    @staticmethod
    def calculate_support_resistance(df: pd.DataFrame, lookback: int = 100) -> pd.DataFrame:
        """
        Calculate support and resistance levels.
        """
        if df.empty or len(df) < lookback:
            return df

        result = df.copy()

        try:
            # Pivot points using recent highs and lows
            recent_high = df['high'].rolling(window=lookback).max()
            recent_low = df['low'].rolling(window=lookback).min()

            result['resistance_1'] = recent_high
            result['support_1'] = recent_low

            # Central pivot
            result['pivot'] = (recent_high + recent_low + df['close']) / 3

            # Secondary S/R levels
            result['resistance_2'] = (recent_high * 2) - recent_low
            result['support_2'] = (recent_low * 2) - recent_high

            # Price position relative to pivot
            result['price_position'] = (df['close'] - result['pivot']) / (result['resistance_1'] - result['support_1'])

        except Exception as e:
            logger.error(f"Error calculating support/resistance: {e}")

        return result

    @staticmethod
    def calculate_trend_strength(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate trend strength indicators.
        """
        if df.empty or len(df) < 20:
            return df

        result = df.copy()

        try:
            # Linear regression slope (simple trend strength)
            x = np.arange(len(df))
            slope = np.polyfit(x, df['close'].values, 1)[0]
            result['trend_slope'] = slope / df['close'].mean()

            # Directional movement
            result['trend_up'] = (df['close'] > df['close'].shift(1)).astype(int)
            result['trend_down'] = (df['close'] < df['close'].shift(1)).astype(int)

            # Trend persistence
            result['trend_persistence'] = result['trend_up'].rolling(window=5).sum() - result['trend_down'].rolling(window=5).sum()

            # Normalized trend strength (-1 to 1)
            result['trend_strength'] = result['trend_persistence'] / 5

        except Exception as e:
            logger.error(f"Error calculating trend strength: {e}")

        return result

    @staticmethod
    def calculate_volatility(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate volatility metrics.
        """
        if df.empty or len(df) < 2:
            return df

        result = df.copy()

        try:
            # True Range
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift())
            low_close = abs(df['low'] - df['close'].shift())

            result['tr'] = high_low.combine(high_close, max).combine(low_close, max)
            result['atr'] = result['tr'].rolling(window=14).mean()

            # Volatility ratio (current ATR / average ATR)
            result['volatility_ratio'] = result['atr'] / result['atr'].rolling(window=50).mean()

            # Normalized volatility
            result['normalized_volatility'] = result['atr'] / df['close'] * 100

        except Exception as e:
            logger.error(f"Error calculating volatility: {e}")

        return result

    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all indicators in one call.
        """
        try:
            # Calculate Heikin-Ashi FIRST
            df = calculate_heikin_ashi(df)
            df = Indicators.calculate_tdi(df)
            df = Indicators.calculate_bollinger_bands(df)
            df = Indicators.calculate_volume_profile(df)
            df = Indicators.calculate_momentum_oscillators(df)
            df = Indicators.calculate_support_resistance(df)
            df = Indicators.calculate_trend_strength(df)
            df = Indicators.calculate_volatility(df)

            return df
        except Exception as e:
            logger.error(f"Error calculating all indicators: {e}")
            return df


__all__ = [
    "Indicators",
    "calculate_heikin_ashi"
]
