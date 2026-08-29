# main.tf

resource "azurerm_resource_group" "this" {
  name     = "rg-cost-analytics"
  location = var.location
}

resource "azurerm_mssql_server" "this" {
  name                         = "sql-cost-analytics-molly" # globally unique
  resource_group_name          = azurerm_resource_group.this.name
  location                     = azurerm_resource_group.this.location
  version                      = "12.0"
  administrator_login          = var.sql_admin_login
  administrator_login_password = var.sql_admin_password
}

resource "azurerm_mssql_database" "analytics" {
  name                        = "sqldb-cost-analytics"
  server_id                   = azurerm_mssql_server.this.id
  sku_name                    = "GP_S_Gen5_1"
  auto_pause_delay_in_minutes = 60
  min_capacity                = 0.5
  max_size_gb                 = 2
}

resource "azurerm_mssql_firewall_rule" "my_ip" {
  name             = "client-ip"
  server_id        = azurerm_mssql_server.this.id
  start_ip_address = var.my_ip
  end_ip_address   = var.my_ip
}
