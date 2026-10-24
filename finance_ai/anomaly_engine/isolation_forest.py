"""
FinGuard AI — Isolation Forest Detector
========================================
Wraps scikit-learn's IsolationForest with:
  • normalised [0, 1] anomaly scores  (1 = most anomalous)
  • joblib serialisation / deserialisation
  • safe handling of unknown / missing feature columns

No Frappe dependency — pure Python + scikit-learn.
"""
from __future__ import annotations

import os
import logging
from typing import List, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler

from finance_ai.anomaly_engine.features import FEATURE_COLUMNS

logger = logging.getLogger(__name__)


class IsolationForestDetector:
    """
    Anomaly detector backed by sklearn's Isolation Forest.

    Anomaly scores are normalised to [0, 1] (higher = more anomalous) so
    they can be directly combined with rule scores in a weighted average.

    Parameters
    ----------
    contamination:
        Expected proportion of anomalies in the training data.
        Passed directly to sklearn's IsolationForest.
    n_estimators:
        Number of base estimators (trees) in the ensemble.
    random_state:
        Random seed for reproducibility.
    """

    #: Feature columns expected by this model.
    FEATURE_COLUMNS: List[str] = FEATURE_COLUMNS

    def __init__(
        self,
        contamination: float = 0.05,
        n_estimators: int = 200,
        random_state: int = 42,
    ) -> None:
        self.contamination = contamination
        self.n_estimators  = n_estimators
        self.random_state  = random_state
        self._model: Optional[IsolationForest]  = None
        self._scaler: Optional[MinMaxScaler]    = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def fit(self, feature_df: pd.DataFrame) -> "IsolationForestDetector":
        """
        Train the Isolation Forest on `feature_df`.

        Parameters
        ----------
        feature_df:
            DataFrame whose columns include FEATURE_COLUMNS.
            Extra columns are ignored; missing columns are zero-filled.

        Returns
        -------
        self  (for method chaining)
        """
        X = self._prepare(feature_df)
        if X.shape[0] < 10:
            raise ValueError(
                f"At least 10 training samples required, got {X.shape[0]}."
            )

        self._model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self._model.fit(X)

        # Fit scaler on training scores so inference scores use the same range
        raw_scores = -self._model.decision_function(X)  # higher = more anomalous
        self._scaler = MinMaxScaler(feature_range=(0.0, 1.0))
        self._scaler.fit(raw_scores.reshape(-1, 1))

        logger.info(
            "IsolationForestDetector trained on %d samples (%d features).",
            X.shape[0], X.shape[1],
        )
        return self

    def score(self, feature_df: pd.DataFrame) -> np.ndarray:
        """
        Return normalised anomaly scores for each row in `feature_df`.

        Scores are in [0, 1]; 1 = most anomalous.

        Parameters
        ----------
        feature_df:
            DataFrame with the same feature columns as training data.

        Returns
        -------
        np.ndarray
            1-D array of floats in [0, 1], length = len(feature_df).

        Raises
        ------
        RuntimeError
            If the model has not been trained yet.
        """
        if self._model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = self._prepare(feature_df)
        raw = -self._model.decision_function(X)

        if self._scaler is not None:
            scores = self._scaler.transform(raw.reshape(-1, 1)).flatten()
        else:
            # Fallback: manual min-max normalisation
            lo, hi = raw.min(), raw.max()
            scores = (raw - lo) / (hi - lo + 1e-9)

        return np.clip(scores, 0.0, 1.0)

    def fit_score(self, feature_df: pd.DataFrame) -> np.ndarray:
        """Convenience method: fit then return scores on the same data."""
        self.fit(feature_df)
        return self.score(feature_df)

    def save(self, path: str) -> None:
        """
        Serialise the trained model to disk with joblib.

        Parameters
        ----------
        path:
            File path for the .pkl file (parent directory must exist).
        """
        if self._model is None:
            raise RuntimeError("Cannot save an unfitted model.")
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        joblib.dump({"model": self._model, "scaler": self._scaler}, path, compress=3)
        logger.info("IsolationForestDetector saved to %s", path)

    @classmethod
    def load(cls, path: str) -> "IsolationForestDetector":
        """
        Load a previously saved detector from disk.

        Parameters
        ----------
        path:
            File path to the .pkl file created by save().

        Returns
        -------
        IsolationForestDetector
            Fitted instance ready to call score() on.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found: {path}")

        data    = joblib.load(path)
        det     = cls()
        det._model  = data["model"]
        det._scaler = data.get("scaler")
        logger.info("IsolationForestDetector loaded from %s", path)
        return det

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _prepare(self, feature_df: pd.DataFrame) -> np.ndarray:
        """
        Select / reindex FEATURE_COLUMNS, fill missing columns with 0,
        and return a float numpy array.
        """
        df = feature_df.reindex(columns=self.FEATURE_COLUMNS, fill_value=0)
        return df.astype(float).to_numpy()
