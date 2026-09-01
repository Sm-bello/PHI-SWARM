"""Edge-native CNN-BiLSTM for quadrotor multi-sensor PHM."""

from __future__ import annotations

import torch
import torch.nn as nn


class UAVPHMModel(nn.Module):
    """
    1D-CNN local features + bidirectional LSTM temporal model + classifier.

    Input:  (batch, seq_len, n_sensors)  with n_sensors=4
    Output: (batch, n_classes) logits
    """

    def __init__(
        self,
        input_dim: int = 4,
        hidden_dim: int = 64,
        num_classes: int = 5,
        num_layers: int = 2,
    ):
        super().__init__()
        self.conv1 = nn.Conv1d(input_dim, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv1d(32, 64, kernel_size=3, padding=1)
        self.relu = nn.ReLU()
        self.pool = nn.MaxPool1d(2, 2)
        self.lstm = nn.LSTM(
            input_size=64,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
        )
        self.fc = nn.Linear(hidden_dim * 2, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, C) -> conv expects (B, C, T)
        x = x.permute(0, 2, 1)
        x = self.pool(self.relu(self.conv1(x)))
        x = self.pool(self.relu(self.conv2(x)))
        x = x.permute(0, 2, 1)
        out, (hn, _) = self.lstm(x)
        # last layer forward + backward hidden
        encoded = torch.cat([hn[-2], hn[-1]], dim=1)
        return self.fc(encoded)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == "__main__":
    m = UAVPHMModel()
    x = torch.randn(8, 64, 4)
    y = m(x)
    print(f"params={count_parameters(m)}  out={tuple(y.shape)}")
