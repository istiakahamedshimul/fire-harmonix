# Architecture and Experiment Protocol

## End-to-end research flow

```mermaid
sequenceDiagram
    participant K as Kaggle / NASA FIRMS
    participant I as Ingestion
    participant H as Harmonization
    participant S as SQLite
    participant M as ML Benchmarks
    participant A as API
    participant U as Dashboard user
    K->>I: MODIS + VIIRS CSV files
    I->>I: Validate coordinates, time, fields, duplicates
    I->>H: Clean observations
    H->>H: Sensor normalization + common grid + HFAI
    H->>S: Observations and analytical views
    S->>M: Chronological daily features
    M->>M: 70/15/15 split, tune, evaluate
    M-->>S: Future inference outputs
    U->>A: Filter or inspect observation
    A->>S: SQL query
    S-->>A: Auditable source + derived values
    A-->>U: Map, calendar, scenario result
```

## Data-layer design

```mermaid
erDiagram
    OBSERVATIONS {
      int id PK
      float latitude
      float longitude
      date acq_date
      string satellite
      string sensor
      float brightness
      float frp
      string grid_id
      float sensor_agreement
      float hfai
      string status
    }
    GRID_DAILY {
      string grid_id
      date acq_date
      int detection_count
      float mean_frp
      float max_frp
      float mean_brightness
      float hfai
      int day_count
      int night_count
    }
    SENSOR_SUMMARY {
      string sensor
      int detections
      float mean_frp
      float mean_brightness
      float mean_agreement
      float mean_hfai
    }
    OBSERVATIONS }o--|| GRID_DAILY : aggregates_into
    OBSERVATIONS }o--|| SENSOR_SUMMARY : summarizes_by
```

## Model lifecycle

```mermaid
flowchart LR
    A[Grid-day history] --> B[Feature engineering]
    B --> C[Chronological split]
    C --> D[Train 70%]
    C --> E[Validate 15%]
    C --> F[Test 15%]
    D --> G[Isolation Forest]
    D --> H[XGBoost candidates]
    E --> I[Select parameters]
    G --> I
    H --> I
    I --> J[Refit train + validation]
    J --> K[Locked test evaluation]
    K --> L[Versioned artifacts + metrics]
    L --> M[Future monitored deployment]
```

## Evaluation contract

- **Harmonization:** compare sensor correlation and distribution alignment before/after normalization.
- **Anomaly ranking:** validate top-ranked events against historical context; do not invent accuracy without labels.
- **Forecasting:** report MAE, RMSE, and R² on the untouched chronological test period against persistence and historical-mean baselines.
- **Explainability:** use importance and, at scale, SHAP values to explain forecast changes.
- **Safety:** communicate “satellite-detected activity,” never “confirmed wildfire,” without authoritative corroboration.

## Production extension

Replace the demonstration sample with multi-year grid-day tables, calculate paired sensor agreement, add weather and fuel-condition covariates, conduct event-based validation, register model/data versions, and monitor drift and missing-sensor coverage.
