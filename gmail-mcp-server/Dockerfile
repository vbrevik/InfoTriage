FROM node:22-slim

WORKDIR /app

# Install the verified Gmail MCP server package (Package Legitimacy Audit: OK/Approved — T-04-SC)
RUN npm install @shinzolabs/gmail-mcp@1.7.4

# SECURITY: No ARG/ENV carrying CLIENT_ID, CLIENT_SECRET, or REFRESH_TOKEN values.
# All credentials are injected at runtime via env_file in docker-compose (NF-6, ADR-008).

COPY gmail-mcp-server/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
