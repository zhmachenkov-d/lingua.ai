# Пакет исследований

Единый итоговый документ (структура по brief §6). Разделы 1–3 заполняются в Фазе A; 4–9 — после подтверждения Фазы A.

## 0. Executive Summary

_Placeholder_

## 1. D1. Современные практики

Таблица по brief §4 D1 / epic R3. Алгоритмы FR-19 / FR-10 / FR-24 — PRD §6.3 и recon mastery/review/remediation; пороги Learned и frequent-error — **R19** ([`r19-mastery-and-error-thresholds.md`](./r19-mastery-and-error-thresholds.md)).

| Практика | Принцип | Как реализуется в агенте | Источник | Метрика проверки |
|----------|---------|--------------------------|----------|------------------|
| Интервальное повторение (FSRS vs SM-2) | FSRS DSR (difficulty / stability / retrievability → `next_review`) лучше предсказывает удержание на уровне item, чем SM-2; «Learned» — продуктовый badge поверх FSRS, не терминальное состояние алгоритма | **Vocabulary / FSRS scheduler** (`pip install fsrs` в D3): расписание карточек; **Learned Word** badge при **S ≥ 21 дн.** и последних **k = 3** успешных retrieval с **≥ 3** разными из 6 drills (R19); runner-up SM-2 + mature только если нужна интерпретируемость ценой прогноза | FSRS wiki / Anki FSRS FAQ / SuperMemo SM-2; recon [1][2][3][12]; **R19** | Удержание на целевом R среди слов с badge; доля активного словаря с badge |
| Comprehensible input / i+1 / ~90% понимания | Вход чуть выше текущего уровня (i+1); целевой ориентир — **~90%** лексем/конструкций ввода уже понятны learner | **CEFR-ограничитель** + проверка покрытия словаря в промптах **Teacher Agent** / Lesson generation (учебник + dictionary-in-context); при оценке понимания ниже ~90% — simplify / gloss, не прыжок «+2 CEFR» | Krashen, *Principles and Practice of Second Language Acquisition* (Input Hypothesis / i+1); CEFR-гейт — продуктовая реализация | Доля Lesson, где оценка понимания ≥ ~90% без fallback; доля «непонятно» / simplify на выборке |
| TBLT (pre-task → main-task → post-task) | Задача с outcome, а не только упражнение; повторение задачи с spacing даёт CAF-эффекты | **Lesson / Topic** как task spine учебника; Stage 2 **TBLT-режим**: pre-task (лексика/модель) → main-task (речь/письмо с целью) → post-task (форма + ошибки); hybrid review (FR-10) — spaced task retrieval | Ellis / Willis TBLT; Bui et al. *System* 2019; recon [6][18] | Успех повторного выполнения того же типа задачи с отсрочкой (CAF / completion) |
| Focus on Form в коммуникативном контексте | Краткая формальная работа внутри смысла (FFI), не отдельный «грамматический курс» в вакууме | **Teacher Agent**: prompt/negotiation-of-form в **Lesson**; **Review Lesson** для системных ошибок; isolated + integrated FFI комплементарны | Long, Focus on Form; Spada & Lightbown 2008; recon [9][21] | Доля исправлений с learner repair (uptake); снижение повторной ошибки того же типа после Review |
| Обучение через ошибки + журнал + отложенная ОС | Ошибки — сигнал select → rewrite → new production; CF даёт средний устойчивый эффект; timing CF не универсален — продукт использует **отложенную** ОС (после задачи / по порогу), не только мгновенный recast | Во время Lesson/Vocab: запись в **Error journal** (тип, Topic) без обязательного мгновенного разбора; **отложенная ОС** — post-task или **Teacher Agent** in-app notify при **≥ 3** ошибках одного типа за **7 дней** (R19 / FR-23); затем remediation **mix** (FR-24): короткий **Review Lesson** или **Vocab Session** + spaced inject | Li 2010 CF meta; Fu & Li 2023 / Li 2025 CF timing; Stillwell error diary; recon [8][11][22][23]; **R19**; PRD §6.3 | Доля ошибок с отложенным (не мгновенным) разбором; повтор того же типа ошибки после окна remediation |
| Микрообучение с генеративным ИИ | Короткие, цель-сфокусированные сессии без перегрузки; лучше сочетать с spaced practice | **Vocab Session** и короткие **Review Lesson**; генерация drills (6 модальностей v1) из словаря/учебника; не длинные «лекции» LLM | Buchem & Hamelmann, *Microlearning: a strategy for ongoing professional development* (2010); L2 spaced practice — Kim & Webb 2022, recon [10] | Доля завершённых коротких сессий; число items за сессию без dropout |
| Формативное оценивание и интерпретируемая ОС | Обратная связь для улучшения, не только балл; интерпретируемость для learner | **Teacher Agent**: объяснения на RU UI; оценки drills → обновление FSRS grades; отчёты «что повторить» (Topic + error types), не голый score | Black & Wiliam, formative assessment; CF timing Fu & Li 2023; recon [22] | Доля сессий с действенной (actionable) ОС; переход ОС → follow-up practice |
| CEFR-выравнивание и mastery-based progression | Уровень по навыкам + mastery без «вечного gate» без spaced практики | **LearnerProfile** CEFR по навыкам; **Next Lesson** gate + hybrid review (FR-10); Learned badge (R19) для лексики; не mastery-gate-alone на Topic | Council of Europe CEFR; Nation / Milton coverage — recon [15][16]; mastery + distribute practice — recon [19] | Отсроченное повторное выполнение Topic; доля Topics после gate с последующим spaced retrieval |
| Обучение на предложениях, не изолированных словах | Лексика в контексте / collocations; предложение важнее списка изолированных слов | **Lesson** и **Vocab Session**: примеры предложений из учебника / dictionary; drills cloze / translate на уровне фразы; dictionary-in-context | Nation, vocabulary size / coverage (recon [15]); Sinclair, idiom principle / collocation; многоаспектная лексика — recon [13][14] | Доля items с sentence context; доля productive drills (cloze/write) vs только match |
| Явное + имплицитное обучение (баланс) | Explicit knowledge + meaning-focused practice; не только правила и не только «погружение» | **Teacher Agent** + планировщик **Lesson**: явное — Focus on Form / **Review Lesson**; имплицитное/смысловое — TBLT main-task, comprehensible input, spaced retrieval в **Vocab Session** | DeKeyser / Ellis, explicit–implicit; Spada & Lightbown — recon [9] | Доля явных vs коммуникативных задач в недельном плане; удержание после обоих типов |

**Ключ источников (recon appendix):** [1]–[23] — `_bmad-output/initiative-research/research-phase-a-learning-algorithms-mastery-revi/research-phase-a-learning-algorithms-mastery-revi.md` § Source appendix. **R19** — пороги Learned и FR-23 в приложении §10.

## 2. D2. Конкурентный анализ

_Placeholder_

## 3. D3. Техническое исследование

_Placeholder_

## 4. D4. Архитектура

_Placeholder_

## 5. D5. Модель данных

_Placeholder_

## 6. D6. Сценарии

_Placeholder_

## 7. D7. Промпты

_Placeholder_

## 8. D8. Roadmap

_Placeholder_

## 9. D9. Риски

_Placeholder_

## 10. Приложения

- R19 thresholds (Learned badge S/k + FR-23 frequency): [`r19-mastery-and-error-thresholds.md`](./r19-mastery-and-error-thresholds.md)
