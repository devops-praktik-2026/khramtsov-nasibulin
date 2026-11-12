# Что описание отдаёт наружу после применения.
# Посмотреть: tofu output
#
# Главный смысл этого файла: отсюда адреса «серверов»
# будут сами попадать в список серверов для сценария настройки, и никто
# больше не будет вписывать их руками.

output "database_url" {
  description = "Готовая строка подключения к базе данных стенда"
  value       = "postgresql+psycopg://${var.db_user}:${var.db_password}@localhost:${var.db_port}/${var.db_name}"
  sensitive   = true
}

output "servers" {
  description = "Учебные «серверы»: имя, порт для входа и порт приложения"
  value = [
    for index, container in docker_container.server : {
      name     = container.name
      ssh_port = var.ssh_base_port + index
      app_port = var.app_base_port + index
    }
  ]
}

output "ansible_inventory" {
  description = "Inventory для Ansible из фактических опубликованных SSH-портов серверов"
  value       = <<-EOT
[app]
%{for index, server in docker_container.server~}
server-${index + 1} ansible_host=${var.ansible_host} ansible_port=${one([for port in server.ports : port.external if port.internal == 22])}
%{endfor~}

[app:vars]
ansible_user=deploy
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null'
EOT
}
