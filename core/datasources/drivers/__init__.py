from core.datasources.drivers.clickhouse import ClickHouseDatasourceDriver
from core.datasources.drivers.mysql import MysqlDatasourceDriver
from core.datasources.drivers.postgres import PostgresDatasourceDriver

PLATFORM_DRIVERS: dict[str, PostgresDatasourceDriver | MysqlDatasourceDriver | ClickHouseDatasourceDriver] = {
    "postgres": PostgresDatasourceDriver(),
    "mysql": MysqlDatasourceDriver(),
    "clickhouse": ClickHouseDatasourceDriver(),
}


def platform_driver(
    connector_id: str,
) -> PostgresDatasourceDriver | MysqlDatasourceDriver | ClickHouseDatasourceDriver:
    driver = PLATFORM_DRIVERS.get(connector_id)
    if driver is None:
        raise ValueError(f"no platform driver for connector_id={connector_id}")
    return driver
