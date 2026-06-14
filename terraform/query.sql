SELECT 
    ticker, 
    ROUND(AVG(momentum_sentiment), 2) as average_sentiment, 
    COUNT(*) as signal_count,
    MAX(confidence_score) as top_confidence
FROM 
    modeled_sentiment
WHERE 
    ticker IS NOT NULL
GROUP BY 
    ticker
ORDER BY 
    average_sentiment DESC;
