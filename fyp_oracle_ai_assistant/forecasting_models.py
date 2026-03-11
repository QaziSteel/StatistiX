"""
Forecasting Models Module
Centralized implementation of all time series forecasting models
"""

import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Import optional packages
try:
    from pmdarima import auto_arima
    HAS_PMDARIMA = True
except ImportError:
    HAS_PMDARIMA = False

try:
    from prophet import Prophet
    HAS_PROPHET = True
except ImportError:
    HAS_PROPHET = False

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False


def rmse(y_true, y_pred):
    """Calculate RMSE"""
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


class ForecastModel(ABC):
    """Base class for all forecasting models"""
    
    @abstractmethod
    def fit(self, train, exog_train=None):
        """Fit the model to training data"""
        pass
    
    @abstractmethod
    def predict(self, steps, exog_test=None):
        """Generate predictions"""
        pass
    
    @abstractmethod
    def get_forecast_frame(self, steps, exog_future=None):
        """Return forecast as DataFrame with confidence intervals"""
        pass


class SARIMAModel(ForecastModel):
    """Seasonal ARIMA Model"""
    
    def __init__(self, order=(1,1,1), seasonal_order=(1,1,1,12)):
        self.order = order
        self.seasonal_order = seasonal_order
        self.model = None
        self.result = None
    
    def fit(self, train, exog_train=None):
        self.model = SARIMAX(
            train,
            exog=exog_train,
            order=self.order,
            seasonal_order=self.seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False
        )
        self.result = self.model.fit(disp=False)
        return self.result
    
    def predict(self, steps, exog_test=None):
        return self.result.get_forecast(steps=steps, exog=exog_test).summary_frame()
    
    def get_forecast_frame(self, steps, exog_future=None):
        return self.result.get_forecast(steps=steps, exog=exog_future).summary_frame()


class ARIMAModel(ForecastModel):
    """ARIMA (non-seasonal) Model"""
    
    def __init__(self, order=(1,1,1)):
        self.order = order
        self.seasonal_order = (0, 0, 0, 0)
        self.model = None
        self.result = None
    
    def fit(self, train, exog_train=None):
        self.model = SARIMAX(
            train,
            exog=exog_train,
            order=self.order,
            seasonal_order=self.seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False
        )
        self.result = self.model.fit(disp=False)
        return self.result
    
    def predict(self, steps, exog_test=None):
        return self.result.get_forecast(steps=steps, exog=exog_test).summary_frame()
    
    def get_forecast_frame(self, steps, exog_future=None):
        return self.result.get_forecast(steps=steps, exog=exog_future).summary_frame()


class SARIMAXModel(ForecastModel):
    """Seasonal ARIMA with eXogenous variables"""
    
    def __init__(self, order=(1,1,1), seasonal_order=(1,1,1,12)):
        self.order = order
        self.seasonal_order = seasonal_order
        self.model = None
        self.result = None
    
    def fit(self, train, exog_train=None):
        if exog_train is None:
            raise ValueError("SARIMAX requires exogenous variables")
        
        self.model = SARIMAX(
            train,
            exog=exog_train,
            order=self.order,
            seasonal_order=self.seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False
        )
        self.result = self.model.fit(disp=False)
        return self.result
    
    def predict(self, steps, exog_test=None):
        if exog_test is None:
            raise ValueError("SARIMAX requires exogenous variables for prediction")
        return self.result.get_forecast(steps=steps, exog=exog_test).summary_frame()
    
    def get_forecast_frame(self, steps, exog_future=None):
        if exog_future is None:
            raise ValueError("SARIMAX requires exogenous variables for forecasting")
        return self.result.get_forecast(steps=steps, exog=exog_future).summary_frame()


class AutoARIMAModel(ForecastModel):
    """Auto ARIMA - automatically selects best ARIMA parameters"""
    
    def __init__(self, seasonal=True, m=12, max_p=5, max_q=5, max_d=2):
        self.seasonal = seasonal
        self.m = m
        self.max_p = max_p
        self.max_q = max_q
        self.max_d = max_d
        self.result = None
        self.best_order = None
        self.best_seasonal_order = None
    
    def fit(self, train, exog_train=None):
        if not HAS_PMDARIMA:
            raise ImportError("pmdarima is required for AutoARIMA. Install with: pip install pmdarima")
        
        self.result = auto_arima(
            train,
            exogenous=exog_train,
            seasonal=self.seasonal,
            m=self.m,
            max_p=self.max_p,
            max_q=self.max_q,
            max_d=self.max_d,
            suppress_warnings=True,
            stepwise=True
        )
        
        self.best_order = self.result.order
        self.best_seasonal_order = self.result.seasonal_order if self.seasonal else (0,0,0,0)
        
        return self.result
    
    def predict(self, steps, exog_test=None):
        # pmdarima's AutoARIMA uses predict() method, not get_forecast()
        predictions = self.result.predict(
            n_periods=steps,
            exogenous=exog_test
        )
        
        # Get in-sample residuals for confidence intervals
        residuals = self.result.resid()
        std_error = float(np.std(residuals)) if len(residuals) > 0 else 1.0
        confidence_interval = 1.96 * std_error  # 95% CI
        
        df = pd.DataFrame({
            'mean': predictions,
            'mean_ci_lower': predictions - confidence_interval,
            'mean_ci_upper': predictions + confidence_interval
        })
        return df
    
    def get_forecast_frame(self, steps, exog_future=None):
        return self.predict(steps, exog_future)


class ExponentialSmoothingModel(ForecastModel):
    """Exponential Smoothing (Holt-Winters) Model"""
    
    def __init__(self, seasonal_periods=12, trend='add', seasonal='add', initialization_method='estimated'):
        self.seasonal_periods = seasonal_periods
        self.trend = trend
        self.seasonal = seasonal
        self.initialization_method = initialization_method
        self.result = None
    
    def fit(self, train, exog_train=None):
        if exog_train is not None:
            print("⚠️ Warning: ExponentialSmoothing ignores exogenous variables")
        
        model = ExponentialSmoothing(
            train,
            seasonal_periods=self.seasonal_periods,
            trend=self.trend,
            seasonal=self.seasonal,
            initialization_method=self.initialization_method
        )
        self.result = model.fit(optimized=True)
        return self.result
    
    def predict(self, steps, exog_test=None):
        forecast = self.result.forecast(steps=steps)
        
        # Calculate simple confidence intervals based on residuals
        residuals = self.result.resid
        std_error = float(np.std(residuals))
        confidence_interval = 1.96 * std_error  # 95% CI
        
        df = pd.DataFrame({
            'mean': forecast,
            'mean_ci_lower': forecast - confidence_interval,
            'mean_ci_upper': forecast + confidence_interval
        })
        return df
    
    def get_forecast_frame(self, steps, exog_future=None):
        forecast = self.result.forecast(steps=steps)
        
        # Calculate simple confidence intervals based on residuals
        residuals = self.result.resid
        std_error = float(np.std(residuals))
        confidence_interval = 1.96 * std_error  # 95% CI
        
        df = pd.DataFrame({
            'mean': forecast,
            'mean_ci_lower': forecast - confidence_interval,
            'mean_ci_upper': forecast + confidence_interval
        })
        return df


class ProphetModel(ForecastModel):
    """Facebook Prophet Model"""
    
    def __init__(self, yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False):
        self.yearly_seasonality = yearly_seasonality
        self.weekly_seasonality = weekly_seasonality
        self.daily_seasonality = daily_seasonality
        self.result = None
        self.train_data = None
    
    def fit(self, train, exog_train=None):
        if not HAS_PROPHET:
            raise ImportError("prophet is required for ProphetModel. Install with: pip install prophet")
        
        # Prepare data for Prophet
        df_train = pd.DataFrame({
            'ds': train.index,
            'y': train.values
        })
        
        if exog_train is not None:
            for col in exog_train.columns:
                df_train[col] = exog_train[col].values
        
        self.train_data = df_train
        
        model = Prophet(
            yearly_seasonality=self.yearly_seasonality,
            weekly_seasonality=self.weekly_seasonality,
            daily_seasonality=self.daily_seasonality
        )
        
        # Add exogenous variables as regressors
        if exog_train is not None:
            for col in exog_train.columns:
                model.add_regressor(col)
        
        # Fit model (suppress_output not supported in newer Prophet)
        import warnings
        import logging
        logging.getLogger('prophet').setLevel(logging.WARNING)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.result = model.fit(df_train)
        return self.result
    
    def predict(self, steps, exog_test=None):
        last_date = self.train_data['ds'].max()
        future_dates = pd.date_range(
            start=last_date + pd.Timedelta(days=1),
            periods=steps,
            freq='D'
        )
        
        future = pd.DataFrame({'ds': future_dates})
        
        if exog_test is not None:
            for col in exog_test.columns:
                future[col] = exog_test[col].values[:steps]
        
        forecast = self.result.predict(future)
        df = pd.DataFrame({
            'mean': forecast['yhat'].values[:steps],
            'mean_ci_lower': forecast['yhat_lower'].values[:steps],
            'mean_ci_upper': forecast['yhat_upper'].values[:steps]
        })
        return df
    
    def get_forecast_frame(self, steps, exog_future=None):
        return self.predict(steps, exog_future)


# ─── Helper Functions for ML Models ────────────────────────────────────────

def create_lag_features(ts: pd.Series, n_lags: int = 12) -> pd.DataFrame:
    """Create lag features for ML time series forecasting"""
    df = pd.DataFrame({'y': ts.values})
    
    for i in range(1, n_lags + 1):
        df[f'lag_{i}'] = ts.shift(i).values
    
    return df.dropna()


class XGBoostModel(ForecastModel):
    """XGBoost Gradient Boosting Model for Time Series"""
    
    def __init__(self, n_lags=12, learning_rate=0.1, max_depth=7, n_estimators=200):
        self.n_lags = n_lags
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.n_estimators = n_estimators
        self.model = None
        self.last_values = None
    
    def fit(self, train, exog_train=None):
        if not HAS_XGBOOST:
            raise ImportError("xgboost is required for XGBoostModel. Install with: pip install xgboost")
        
        # Create lag features
        X = create_lag_features(train, self.n_lags)
        y = X['y'].values
        X = X.drop('y', axis=1).values
        
        # Add exogenous variables if provided
        if exog_train is not None:
            exog_aligned = exog_train.iloc[self.n_lags:].values
            X = np.hstack([X, exog_aligned])
        
        # Train model
        self.model = xgb.XGBRegressor(
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            n_estimators=self.n_estimators,
            random_state=42,
            verbosity=0
        )
        self.model.fit(X, y, verbose=False)
        
        # Store last values for forecasting
        self.last_values = train.iloc[-self.n_lags:].values
        
        return self.model
    
    def predict(self, steps, exog_test=None):
        predictions = []
        current_lags = list(self.last_values)
        
        for i in range(steps):
            # Prepare features
            X_pred = np.array(current_lags).reshape(1, -1)
            
            # Add exogenous if provided
            if exog_test is not None and i < len(exog_test):
                X_pred = np.hstack([X_pred, exog_test.iloc[i:i+1].values])
            
            # Predict
            pred = self.model.predict(X_pred)[0]
            predictions.append(pred)
            
            # Update lags
            current_lags = current_lags[1:] + [pred]
        
        predictions = np.array(predictions)
        std_error = np.std(predictions) * 0.15  # Simple CI estimate
        
        df = pd.DataFrame({
            'mean': predictions,
            'mean_ci_lower': predictions - 1.96 * std_error,
            'mean_ci_upper': predictions + 1.96 * std_error
        })
        return df
    
    def get_forecast_frame(self, steps, exog_future=None):
        return self.predict(steps, exog_future)


class LightGBMModel(ForecastModel):
    """LightGBM Gradient Boosting Model for Time Series"""
    
    def __init__(self, n_lags=12, learning_rate=0.05, max_depth=7, n_estimators=200):
        self.n_lags = n_lags
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.n_estimators = n_estimators
        self.model = None
        self.last_values = None
    
    def fit(self, train, exog_train=None):
        if not HAS_LIGHTGBM:
            raise ImportError("lightgbm is required for LightGBMModel. Install with: pip install lightgbm")
        
        # Create lag features
        X = create_lag_features(train, self.n_lags)
        y = X['y'].values
        X = X.drop('y', axis=1).values
        
        # Add exogenous variables if provided
        if exog_train is not None:
            exog_aligned = exog_train.iloc[self.n_lags:].values
            X = np.hstack([X, exog_aligned])
        
        # Train model
        self.model = lgb.LGBMRegressor(
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            n_estimators=self.n_estimators,
            random_state=42,
            verbose=-1
        )
        self.model.fit(X, y)
        
        # Store last values for forecasting
        self.last_values = train.iloc[-self.n_lags:].values
        
        return self.model
    
    def predict(self, steps, exog_test=None):
        predictions = []
        current_lags = list(self.last_values)
        
        for i in range(steps):
            # Prepare features
            X_pred = np.array(current_lags).reshape(1, -1)
            
            # Add exogenous if provided
            if exog_test is not None and i < len(exog_test):
                X_pred = np.hstack([X_pred, exog_test.iloc[i:i+1].values])
            
            # Predict
            pred = self.model.predict(X_pred)[0]
            predictions.append(pred)
            
            # Update lags
            current_lags = current_lags[1:] + [pred]
        
        predictions = np.array(predictions)
        std_error = np.std(predictions) * 0.15  # Simple CI estimate
        
        df = pd.DataFrame({
            'mean': predictions,
            'mean_ci_lower': predictions - 1.96 * std_error,
            'mean_ci_upper': predictions + 1.96 * std_error
        })
        return df
    
    def get_forecast_frame(self, steps, exog_future=None):
        return self.predict(steps, exog_future)


def get_model(model_type: str, **kwargs) -> ForecastModel:
    """Factory function to get model instance
    
    Args:
        model_type: 'ARIMA', 'SARIMA', 'SARIMAX', 'AUTO_ARIMA', 'EXP_SMOOTHING', 'PROPHET', 'XGBOOST', 'LIGHTGBM'
        **kwargs: Model-specific parameters
    
    Returns:
        ForecastModel instance
    """
    
    model_map = {
        'ARIMA': ARIMAModel,
        'SARIMA': SARIMAModel,
        'SARIMAX': SARIMAXModel,
        'AUTO_ARIMA': AutoARIMAModel,
        'EXP_SMOOTHING': ExponentialSmoothingModel,
        'PROPHET': ProphetModel,
        'XGBOOST': XGBoostModel,
        'LIGHTGBM': LightGBMModel,
    }
    
    if model_type not in model_map:
        raise ValueError(f"Unknown model type: {model_type}. Available: {list(model_map.keys())}")
    
    return model_map[model_type](**kwargs)


def run_forecast(ts: pd.Series, model_type: str, horizon: int, m: int = 12, 
                 exog=None, exog_future=None, test_pct: int = 20, model_params: dict = None):
    """
    Unified forecast function supporting all model types
    
    Args:
        ts: Time series (pd.Series)
        model_type: Model type string
        horizon: Forecast horizon
        m: Seasonality period (default 12 for monthly)
        exog: Exogenous variables for training
        exog_future: Exogenous variables for forecasting
        test_pct: Test set percentage
        model_params: Additional model parameters
    
    Returns:
        Tuple: (model_result, train, test, yhat_test, forecast_df, metrics)
    """
    
    ts = ts.dropna()
    n = len(ts)
    n_test = max(1, int(n * test_pct / 100))
    train, test = ts.iloc[:-n_test], ts.iloc[-n_test:]
    
    exog_train = exog.iloc[:-n_test] if exog is not None else None
    exog_test = exog.iloc[-n_test:] if exog is not None else None
    
    # Get model parameters
    if model_params is None:
        model_params = {}
    
    # Instantiate and fit model
    model = get_model(model_type, **model_params)
    result = model.fit(train, exog_train)
    
    # Get test predictions
    pred_test = model.predict(len(test), exog_test)
    yhat_test = pred_test["mean"].values
    
    # Calculate metrics
    metrics = {
        "MAE": float(mean_absolute_error(test.values, yhat_test)),
        "RMSE": rmse(test.values, yhat_test),
        "model_type": model_type,
        "n_points": int(n),
        "n_train": len(train),
        "n_test": len(test),
        "model_params": model_params
    }
    
    # Generate forecast
    fc = model.get_forecast_frame(int(horizon), exog_future)
    
    return result, train, test, yhat_test, fc, metrics
