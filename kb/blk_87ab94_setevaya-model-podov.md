---
id: blk_87ab94
course: 1
title: Сетевая модель подов
tags: [net, k8s]
sources: [book:1#ch2]
review: {ease: 2.5, interval: 1, due: null}
---

# Сетевая модель подов

## Тезисы

- У каждого пода свой IP в CNI-сети
- Наружу — через Service, kube-proxy балансирует
- DNS внутри кластера резолвит сервисы

## Как я это понял

- Под — как мини-ВМ со своим адресом, сервис — розетка в стене

## Схема

```mermaid
graph LR
  P[Pod] --> S[Service]
  S --> N[Internet]
```
