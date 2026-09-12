# Contributing

Changes should be small, reviewable, and tied to one of the three release use
cases or a documented security/operability requirement.

1. Create a branch from the current release baseline.
2. Add or update tests for changed behaviour.
3. Run `make check` and `make docker-config`.
4. Describe security, data-flow, migration, and compatibility impact in the
   pull request.
5. Do not add a new provider, integration, deployment target, or user-facing
   module without a release-scope decision.

Never commit credentials, production data, customer evidence, or model outputs
containing sensitive information.
