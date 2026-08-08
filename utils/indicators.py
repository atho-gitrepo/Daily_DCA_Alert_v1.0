"""
Technical Indicators for DCA Day Trading
Includes Super TDI + Bollinger Bands + Heikin-Ashi
Version: 1.0.1 - FIXED Heikin-Ashi calculation
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

    This implementation is robust and handles edge cases.
    """
    if df is None or df.empty:
        logger.warning("DataFrame is None or empty for Heikin-Ashi calculation")
        return df if df is not None else pd.DataFrame()

    if len(df) < 2:
        logger.warning(f"DataFrame too small for Heikin-Ashi: {len(df)} rows")
        return df.copy()

    # Check required columns
    required_cols = ['open', 'high', 'low', 'close']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        logger.error(f"Missing required columns for Heikin-Ashi: {missing_cols}")
        return df.copy()

    # Create a fresh copy to avoid modifying original
    ha_df = df.copy()

    try:
        # Calculate Heikin-Ashi using vectorized operations
        # HA Close = (Open + High + Low + Close) / 4
        ha_close = (ha_df['open'] + ha_df['high'] + ha_df['low'] + ha_df['close']) / 4

        # HA Open = (Previous HA Open + Previous HA Close) / 2
        # For the first row, use the regular open
        ha_open_shifted = (ha_df['open'].shift(1) + ha_df['close'].shift(1)) / 2
        ha_open = ha_open_shifted.copy()
        if len(ha_open) > 0:
            ha_open.iloc[0] = ha_df['open'].iloc[0]

        # HA High = max(High, HA Open, HA Close)
        ha_high = pd.DataFrame({
            'high': ha_df['high'],
            'ha_open': ha_open,
            'ha_close': ha_close
        }).max(axis=1)

        # HA Low = min(Low, HA Open, HA Close)
        ha_low = pd.DataFrame({
            'low': ha_df['low'],
            'ha_open': ha_open,
            'ha_close': ha_close
        }).min(axis=1)

        # Assign all HA columns at once
        ha_df['ha_close'] = ha_close
        ha_df['ha_open'] = ha_open
        ha_df['ha_high'] = ha_high
        ha_df['ha_low'] = ha_low

        # HA Color: 1 = Bullish, -1 = Bearish
        ha_df['ha_color'] = np.where(ha_close >= ha_open, 1, -1)

        # HA Body size
        ha_df['ha_body'] = np.abs(ha_close - ha_open)

        # HA Upper and Lower wicks
        ha_df['ha_upper_wick'] = ha_high - ha_df[['ha_open', 'ha_close']].max(axis=1)
        ha_df['ha_lower_wick'] = ha_df[['ha_open', 'ha_close']].min(axis=1) - ha_low

        # HA Trend: 1 = Uptrend, -1 = Downtrend, 0 = Neutral
        ha_df['ha_trend'] = np.where(
            ha_close > ha_open,
            1,
            np.where(ha_close < ha_open, -1, 0)
        )

        # HA Momentum: Difference between HA Close and HA Open
        ha_df['ha_momentum'] = ha_close - ha_open

        # HA Close change percentage
        ha_df['ha_close_pct'] = ha_close.pct_change() * 100

        logger.debug(f"Heikin-Ashi calculated successfully with {len(ha_df)} rows")

    except Exception as e:
        logger.error(f"Error calculating Heikin-Ashi: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Return original DataFrame with HA columns filled with default values
        ha_df['ha_close'] = ha_df['close']
        ha_df['ha_open'] = ha_df['open']
        ha_df['ha_high'] = ha_df['high']
        ha_df['ha_low'] = ha_df['low']
        ha_df['ha_color'] = 0
        ha_df['ha_body'] = 0.0
        ha_df['ha_upper_wick'] = 0.0
        ha_df['ha_lower_wick'] = 0.0
        ha_df['ha_trend'] = 0
        ha_df['ha_momentum'] = 0.0
        ha_df['ha_close_pct'] = 0.0

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
        """
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()

        if len(df) < max(slow_period, fast_period, signal_period) + 1:
            logger.warning(f"DataFrame too small for TDI: {len(df)} rows")
            return df.copy()

        result = df.copy()

        try:
            # 1. Calculate RSI
            rsi_period = 13
            delta = result['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()

            # Avoid division by zero
            loss = loss.replace(0, np.nan)
            rs = gain / loss
            result['tdi_rsi'] = 100 - (100 / (1 + rs))
            result['tdi_rsi'] = result['tdi_rsi'].fillna(50)

            # 2. RSI-based Moving Averages
            result['tdi_fast_ma'] = result['tdi_rsi'].rolling(window=fast_period).mean()
            result['tdi_slow_ma'] = result['tdi_rsi'].rolling(window=slow_period).mean()

            # 3. Volatility Bands
            tdi_std = result['tdi_rsi'].rolling(window=signal_period).std()
            result['tdi_upper_band'] = result['tdi_slow_ma'] + (2.0 * tdi_std)
            result['tdi_lower_band'] = result['tdi_slow_ma'] - (2.0 * tdi_std)

            # 4. TDI Signal
            result['tdi_signal'] = result['tdi_slow_ma'].rolling(window=7).mean()

            # 5. TDI Crossover Signals
            result['tdi_cross_fast'] = np.where(
                result['tdi_fast_ma'] > result['tdi_slow_ma'], 1,
                np.where(result['tdi_fast_ma'] < result['tdi_slow_ma'], -1, 0)
            )

            # 6. TDI Zone
            result['tdi_zone'] = result['tdi_slow_ma']

            # 7. TDI Strength
            result['tdi_momentum'] = result['tdi_rsi'] - result['tdi_slow_ma']

            # 8. TDI Trend Score
            result['tdi_trend_score'] = (
                (result['tdi_fast_ma'] > result['tdi_slow_ma']).astype(int) * 2 +
                (result['tdi_rsi'] > 50).astype(int) * 1
            )

            # 9. TDI Signal Strength
            result['tdi_signal_strength'] = abs(result['tdi_momentum']) / 50

            # Fill NaN values
            for col in ['tdi_rsi', 'tdi_fast_ma', 'tdi_slow_ma', 'tdi_upper_band',
                       'tdi_lower_band', 'tdi_signal', 'tdi_momentum', 'tdi_signal_strength']:
                if col in result.columns:
                    result[col] = result[col].fillna(50)

        except Exception as e:
            logger.error(f"Error calculating TDI: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Set default values
            for col in ['tdi_rsi', 'tdi_fast_ma', 'tdi_slow_ma', 'tdi_upper_band',
                       'tdi_lower_band', 'tdi_signal', 'tdi_momentum', 'tdi_signal_strength']:
                result[col] = 50

        return result

    @staticmethod
    def calculate_bollinger_bands(df: pd.DataFrame, period: int = 34,
                                  dev: float = 1.750) -> pd.DataFrame:
        """
        Calculate Bollinger Bands with standard deviation.
        """
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()

        if len(df) < period + 1:
            logger.warning(f"DataFrame too small for Bollinger Bands: {len(df)} rows")
            return df.copy()

        result = df.copy()

        try:
            result['bb_ma'] = result['close'].rolling(window=period).mean()
            result['bb_std'] = result['close'].rolling(window=period).std()
            result['bb_upper'] = result['bb_ma'] + (dev * result['bb_std'])
            result['bb_lower'] = result['bb_ma'] - (dev * result['bb_std'])
            result['bb_width'] = result['bb_upper'] - result['bb_lower']
            result['bb_width_percent'] = result['bb_width'] / result['bb_ma']
            result['bb_position'] = (result['close'] - result['bb_lower']) / result['bb_width']
            result['bb_percent_b'] = (result['close'] - result['bb_lower']) / (result['bb_upper'] - result['bb_lower'])

            # Fill NaN values
            result['bb_position'] = result['bb_position'].fillna(0.5)
            result['bb_percent_b'] = result['bb_percent_b'].fillna(0.5)
            result['bb_width_percent'] = result['bb_width_percent'].fillna(0.01)

        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {e}")

        return result

    @staticmethod
    def calculate_volume_profile(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """Calculate volume-based indicators."""
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()

        result = df.copy()

        try:
            result['volume_ma'] = result['volume'].rolling(window=period).mean()
            result['volume_ratio'] = result['volume'] / result['volume_ma']
            result['volume_ratio'] = result['volume_ratio'].fillna(1.0)
            result['volume_spike'] = result['volume_ratio'] > 1.5

            # VWAP calculation
            typical_price = (result['high'] + result['low'] + result['close']) / 3
            result['vwap'] = (typical_price * result['volume']).cumsum() / result['volume'].cumsum()
            result['vwap'] = result['vwap'].fillna(result['close'])

        except Exception as e:
            logger.error(f"Error calculating volume profile: {e}")

        return result

    @staticmethod
    def calculate_momentum_oscillators(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate momentum oscillators for entry confirmation."""
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()

        if len(df) < 14:
            return df.copy()

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
            loss = loss.replace(0, np.nan)
            rs = gain / loss
            result['rsi'] = 100 - (100 / (1 + rs))
            result['rsi'] = result['rsi'].fillna(50)

            # Stochastic Oscillator
            low_14 = result['low'].rolling(window=14).min()
            high_14 = result['high'].rolling(window=14).max()
            result['stoch_k'] = 100 * ((result['close'] - low_14) / (high_14 - low_14))
            result['stoch_d'] = result['stoch_k'].rolling(window=3).mean()
            result['stoch_k'] = result['stoch_k'].fillna(50)
            result['stoch_d'] = result['stoch_d'].fillna(50)

        except Exception as e:
            logger.error(f"Error calculating momentum oscillators: {e}")

        return result

    @staticmethod
    def calculate_support_resistance(df: pd.DataFrame, lookback: int = 100) -> pd.DataFrame:
        """Calculate support and resistance levels."""
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()

        if len(df) < lookback:
            return df.copy()

        result = df.copy()

        try:
            recent_high = df['high'].rolling(window=lookback).max()
            recent_low = df['low'].rolling(window=lookback).min()
            result['resistance_1'] = recent_high
            result['support_1'] = recent_low
            result['pivot'] = (recent_high + recent_low + df['close']) / 3
            result['resistance_2'] = (recent_high * 2) - recent_low
            result['support_2'] = (recent_low * 2) - recent_high
            result['price_position'] = (df['close'] - result['pivot']) / (result['resistance_1'] - result['support_1'])

        except Exception as e:
            logger.error(f"Error calculating support/resistance: {e}")

        return result

    @staticmethod
    def calculate_trend_strength(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate trend strength indicators."""
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()

        if len(df) < 20:
            return df.copy()

        result = df.copy()

        try:
            x = np.arange(len(df))
            slope = np.polyfit(x, df['close'].values, 1)[0]
            result['trend_slope'] = slope / df['close'].mean()
            result['trend_up'] = (df['close'] > df['close'].shift(1)).astype(int)
            result['trend_down'] = (df['close'] < df['close'].shift(1)).astype(int)
            result['trend_persistence'] = result['trend_up'].rolling(window=5).sum() - result['trend_down'].rolling(window=5).sum()
            result['trend_strength'] = result['trend_persistence'] / 5
            result['trend_strength'] = result['trend_strength'].fillna(0)

        except Exception as e:
            logger.error(f"Error calculating trend strength: {e}")

        return result

    @staticmethod
    def calculate_volatility(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate volatility metrics."""
        if df is None or df.empty:
            return df if df is not None else pd.DataFrame()

        if len(df) < 2:
            return df.copy()

        result = df.copy()

        try:
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift())
            low_close = abs(df['low'] - df['close'].shift())
            result['tr'] = high_low.combine(high_close, max).combine(low_close, max)
            result['atr'] = result['tr'].rolling(window=14).mean()
            result['volatility_ratio'] = result['atr'] / result['atr'].rolling(window=50).mean()
            result['normalized_volatility'] = result['atr'] / df['close'] * 100

            # Fill NaN values
            result['volatility_ratio'] = result['volatility_ratio'].fillna(1.0)
            result['normalized_volatility'] = result['normalized_volatility'].fillna(0)

        except Exception as e:
            logger.error(f"Error calculating volatility: {e}")

        return result

    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all indicators in one call with proper error handling.
        """
        if df is None or df.empty:
            logger.warning("Empty or None DataFrame passed to calculate_all_indicators")
            return df if df is not None else pd.DataFrame()

        # Create a working copy
        work_df = df.copy()

        try:
            # Step 1: Calculate Heikin-Ashi FIRST (most important)
            work_df = calculate_heikin_ashi(work_df)

            # Verify HA columns were created
            required_ha_cols = ['ha_open', 'ha_close', 'ha_high', 'ha_low', 'ha_color']
            missing_ha = [col for col in required_ha_cols if col not in work_df.columns]
            if missing_ha:
                logger.warning(f"Missing HA columns after calculation: {missing_ha}")
                # Create default HA columns if missing
                work_df['ha_open'] = work_df['open']
                work_df['ha_close'] = work_df['close']
                work_df['ha_high'] = work_df['high']
                work_df['ha_low'] = work_df['low']
                work_df['ha_color'] = 0
                work_df['ha_body'] = 0.0
                work_df['ha_upper_wick'] = 0.0
                work_df['ha_lower_wick'] = 0.0
                work_df['ha_trend'] = 0
                work_df['ha_momentum'] = 0.0
                work_df['ha_close_pct'] = 0.0

            # Step 2: Calculate TDI
            work_df = Indicators.calculate_tdi(work_df)

            # Step 3: Calculate Bollinger Bands
            work_df = Indicators.calculate_bollinger_bands(work_df)

            # Step 4: Calculate Volume Profile
            work_df = Indicators.calculate_volume_profile(work_df)

            # Step 5: Calculate Momentum Oscillators
            work_df = Indicators.calculate_momentum_oscillators(work_df)

            # Step 6: Calculate Support/Resistance
            work_df = Indicators.calculate_support_resistance(work_df)

            # Step 7: Calculate Trend Strength
            work_df = Indicators.calculate_trend_strength(work_df)

            # Step 8: Calculate Volatility
            work_df = Indicators.calculate_volatility(work_df)

            logger.debug(f"All indicators calculated successfully for {len(work_df)} rows")

        except Exception as e:
            logger.error(f"Error calculating all indicators: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Ensure essential columns exist even if calculation fails
            essential_cols = ['ha_open', 'ha_close', 'ha_high', 'ha_low', 'ha_color',
                            'tdi_rsi', 'tdi_fast_ma', 'tdi_slow_ma', 'tdi_zone',
                            'bb_ma', 'bb_upper', 'bb_lower', 'bb_position']
            for col in essential_cols:
                if col not in work_df.columns:
                    if col.startswith('ha_'):
                        if col == 'ha_open':
                            work_df[col] = work_df['open']
                        elif col == 'ha_close':
                            work_df[col] = work_df['close']
                        elif col == 'ha_high':
                            work_df[col] = work_df['high']
                        elif col == 'ha_low':
                            work_df[col] = work_df['low']
                        elif col == 'ha_color':
                            work_df[col] = 0
                    elif col in ['tdi_rsi', 'tdi_fast_ma', 'tdi_slow_ma', 'tdi_zone']:
                        work_df[col] = 50
                    elif col in ['bb_ma', 'bb_upper', 'bb_lower']:
                        work_df[col] = work_df['close']
                    elif col == 'bb_position':
                        work_df[col] = 0.5

        return work_df


__all__ = [
    "Indicators",
    "calculate_heikin_ashi"
]
