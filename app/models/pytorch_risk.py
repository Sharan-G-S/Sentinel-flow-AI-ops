from __future__ import annotations

import torch
import torch.nn as nn
import torch.optim as optim


class RiskNet(nn.Module):
    def __init__(self, input_dim: int = 3):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 8),
            nn.ReLU(),
            nn.Linear(8, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class PyTorchRiskModel:
    """
    Online-friendly risk predictor estimating incident escalation probability.
    """

    def __init__(self):
        self.model = RiskNet(input_dim=3)
        self.loss_fn = nn.BCELoss()
        self.optimizer = optim.Adam(self.model.parameters(), lr=0.01)
        self._warmup_train()

    def _warmup_train(self) -> None:
        # [metric_value, anomaly_score, error_rate]
        x = torch.tensor(
            [
                [40.0, 0.05, 0.01],
                [45.0, 0.10, 0.03],
                [60.0, 0.30, 0.05],
                [75.0, 0.65, 0.11],
                [90.0, 0.80, 0.19],
                [95.0, 0.95, 0.30],
            ],
            dtype=torch.float32,
        )
        y = torch.tensor([[0.0], [0.0], [0.0], [1.0], [1.0], [1.0]], dtype=torch.float32)
        for _ in range(400):
            pred = self.model(x)
            loss = self.loss_fn(pred, y)
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()

    def predict_risk(self, metric_value: float, anomaly_score: float, error_rate: float) -> float:
        with torch.no_grad():
            features = torch.tensor(
                [[metric_value, anomaly_score, error_rate]], dtype=torch.float32
            )
            score = self.model(features).item()
        return max(0.0, min(1.0, float(score)))
