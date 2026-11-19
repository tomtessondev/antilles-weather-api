# Roadmap

1. **Weather API** (done). The batch marts loaded daily into Neon, served by FastAPI on
   Cloud Run behind API keys and quotas, deployed from GitHub Actions without keys.
2. **Hurricane passages.** Serve the warehouse's storm passages near each island (BigQuery
   marts exported daily), with the same keys and caching.
3. **Usage per key.** Count calls per key and day in the database (batched, so Neon stays
   asleep) and show them with `weather-api keys list`.
4. **Client library.** A typed Python client generated from the OpenAPI schema, published
   with the repository.
