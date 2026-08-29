terraform {
  backend "azurerm" {
    resource_group_name  = "rg-tfstate"
    storage_account_name = "sttfstatemolly"
    container_name       = "tfstate"
    key                  = "cost-analytics.tfstate"
  }
}
