"""Sample local configuration for connecting to SQL Server.

Copy this file to `config_local.py` and update the values as needed.
"""

SQLSERVER_ODBC = (
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=NRFVMSSQL04;"
    "Database=NRF_REPORTS;"
    "Trusted_Connection=Yes;"
    "Encrypt=no;"
)

# If your SQL Server requires TLS with no CA:
# SQLSERVER_ODBC = (
#     "Driver={ODBC Driver 18 for SQL Server};"
#     "Server=NRFVMSSQL04;"
#     "Database=NRF_REPORTS;"
#     "Trusted_Connection=Yes;"
#     "Encrypt=yes;TrustServerCertificate=yes;"
# )
