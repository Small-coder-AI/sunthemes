---
name: registry-writes-by-user-only
description: Запись в HKCU Run (автозагрузка) мне напрямую нельзя — делает Руслан руками или приложение через галку в UI
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9b07eb30-f830-47c5-8e53-a42560a8f72e
---

Попытка `Set-ItemProperty HKCU:\...\Run` из Bash/PowerShell была отклонена classifier'ом ([Unauthorized Persistence]).

**Why:** автозапуск через реестр — паттерн persistence, авто-режим это блокирует независимо от намерений.

**How to apply:** для изменения автозагрузки давать Руслану готовую команду (он выполняет сам) либо использовать штатную галку автозагрузки в UI приложения [[sunthemes-project-state]]. Не пытаться писать Run-ключ напрямую.
