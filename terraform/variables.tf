
variable "location" {
  type        = string
  description = "Azure region for all resources"
  default     = "westus2"
}

variable "sql_admin_login" {
  type        = string
  description = "Administrator login name for the SQL server"
}

variable "sql_admin_password" {
  type        = string
  description = "Administrator password for the SQL server"
  sensitive   = true
}

variable "my_ip" {
  type        = string
  description = "Client public IP allowed through SQL firewall"
}
