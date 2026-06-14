CREATE EXTERNAL TABLE IF NOT EXISTS modeled_sentiment (
  ticker string,
  momentum_sentiment double,
  catalyst_mentioned string,
  confidence_score double
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://momentum-intel-lakehouse-structured-stage/modeled_sentiment/';
