# ub-mode — принципы написания кода (русский перевод)

Источник: [unclebob/ub-mode](https://github.com/unclebob/ub-mode), файл `SKILL.md`
(Роберт Мартин, октябрь 2026). Перевод полный, для внутренней разработки LearnOS.
Оригинал — в конце файла.

Адаптация под наш стек: у оригинала есть инструменты-компаньоны
(`crapper` — сложность/CRAP, `dryer` — дубликаты, `mutator` — мутационное
тестирование). Мы их не портируем; их роль закрывают наши обязательные проверки
(`ruff`, `mypy`, `lint-imports`, `pytest` + список обязательных тестов из
[07-code-standards.md](../07-code-standards.md)) и ревью дублей на глаз.
Там, где скилл говорит «use the crapper tool», читай «прогони наши проверки
и не оставляй функцию, которая их заваливает».

---

# ub-mode (перевод)

Каждый раз, когда тебя просят что-то изменить, действуй так:

* Сначала заставь это работать.
* Потом сделай это правильным.
* Следуй практике.

# Сначала заставь это работать

## Протокол лени

* Одно решение живёт в одном месте.
* Поставь минимальную правку, которая решает проблему.

## Фундаментальное мышление

* Сначала добейся правильной формы данных, потом пиши логику.
* Делай в первую очередь то, что поможет всем последующим фазам.
* Если одновременный писатель имел бы значение — не дели состояние.

## TDD

* Пиши падающий тест до того, как менять код.
* Убедись, что он падает по ожидаемой причине.
* Сделай минимальное изменение, которое его чинит.
* Если честный тест нецелесообразен — не пиши плохой вместо него.

## Перепроектируй с первых принципов

* Не прикручивай новое требование к старому дизайну.
* Спроси себя: что бы ты построил, если бы это требование было здесь с самого
  начала, продумай это и доставляй кусками.

## Атакуй предпосылку

* Когда два фикса, построенных на одной предпосылке, валятся об один и тот же
  шлюз — запиши эту предпосылку одним предложением и посчитай, на чьей стороне
  перекос.
* Убери само это распределение обязанностей.
* Не начинай следующий фикс, пока не сделал этого.

## Сначала вычти, потом добавляй

* Убирай сложность до того, как что-то добавлять.

## Исполнение с прицелом на результат

* Целься в конечное состояние, которое можно проверить.
* Разрыв посередине допустим, если ты его запланировал и можешь откатить.

## Построй рычаг

* Если работу не видишь с одного взгляда — построй инструмент, который её делает.
* Сделай одну единицу руками, затем заставь инструмент повторять именно её.

## Архитектура

### Смоделируй домен

* Помести домен в структуру, в которой невозможные состояния невозможны.
* Веди глоссарий доменных терминов.
* Если код уже ясен и локален — оставь как есть.

### Дисциплина границ

* Проверяй данные там, где они входят.
* Внутри — доверяй им.
* Бизнес-логику держи в чистой функции.

### Дисциплина типов

* Сделай невозможным записать незаконное значение.
* Разбирай внешние данные один раз, на входе.
* Не заглушай компилятор.

### Сделай операции идемпотентными

* Два запуска, или запуск после падения посередине, приводят в одно и то же
  состояние.

### Сначала раздели, потом сериализуй общее состояние

* Если им не нужно одно и то же изменяемое — дай каждому своё.
* Если нужно — оставь одного писателя и закрепи это в структуре.

# Потом сделай это правильным

## Устрани корневую причину

* Воспроизведи.
* Почини причину.
* Стража, которая лишь прячет падение, — не фикс.

## Разбей работу на проверяемые единицы

* Заверши одну маленькую единицу и проверь её.
* Потом начинай следующую.

## Тестируй поведение, а не реализацию

* Тест зовёт код так, как его зовёт пользователь, и проверяет результат,
  который увидел бы пользователь.
* Если тест остался бы зелёным, если бы каждая функция возвращала пустоту, —
  выбрось его.

## Сложность (в оригинале — инструмент crapper)

* Прогони проверки сложности/покрытия.
* Каждую функцию с CRAP ≥ 10 уменьши: раздели, покрой тестами, или и то и другое.
* Подумай, стоит ли ужимать разборы case-выражений.

## Дубликаты (в оригинале — инструмент dryer)

* Найди и убери дубликацию ранга 0.8 и выше.

## Мутации (в оригинале — инструмент mutator)

* Покрой непокрытое.
* Убей выживших (мутантов).
* Удали мёртвый код.

## Рефакторинг

* Зафиксируй, что код делает.
* Измени структуру.
* Докажи, что поведение не изменилось.

# Следуй практике

## Веди журнал

* Записывай каждое действие и причину, по которой ты его сделал.
* Отчитайся этим журналом по завершении.

## Береги окно контекста

* Держи главный поток маленьким.
* Основную массу отправляй куда-то ещё, себе оставляй саммари.

## Уборка рабочей копии

* Найди, что безопасно убрать; убедись, что ничего из живого это не использует;
  только потом освобождай место.
* Незакоммиченная работа ждёт решения.

## Коммить и пушь

* Коммить часто, маленькими упорядоченными коммитами.
* Каждый коммит говорит: почему, что изменилось и как ты это доказал.
* Пушь в основную ветку в конце.

---

# Оригинал (для сверки)

```markdown
# ub-mode

Every time you are asked to make a change follow:
* First Make it Work.
* Then Make it Right.
* Follow Practice

# First Make it Work

## Laziness Protocol
* One decision lives in one place.
* Ship the smallest edit that solves the problem.

## Foundational Thinking
* Get the data shape right before you write the logic.
* Do first whatever helps every later phase.
* If a concurrent writer would matter, do not share state.

## TDD
* Write the failing test before you change the code.
* See it fail for the reason you expect.
* Make the smallest change that makes it pass.
* If an honest test is impractical, do not write a bad one.

## Redesign From First Principles
* Do not bolt a new requirement onto the old design.
* Ask what you would have built if it had been there from the start, think that
  through, and deliver it in pieces.

## Attack the Premise
* When two fixes that share one premise fail the same gate, write that premise
  in one sentence and count which actors hold the imbalance.
* Remove the assignment.
* Do not start another fix until you have done that.

## Subtract Before You Add
* Take complexity out before you add anything.

## Outcome-Oriented Execution
* Aim at the end state you can check.
* A break in the middle is allowed when you planned it and can undo it.

## Build the Lever
* If the work is not obvious at a glance, build the tool that does it.
* Do one unit by hand, then make the tool match that unit.

## Architecture

### Model the Domain
* Put the domain in a structure that makes the illegal states impossible.
* Maintain a glossary of domain terms.
* If the code is already clear and local, leave it.

### Boundary Discipline
* Check the data where it enters.
* Inside, trust it.
* Keep the business logic in a pure function.

### Type System Discipline
* Make the illegal value impossible to write.
* Parse outside data once, where it comes in.
* Do not silence the compiler.

### Make Operations Idempotent
* Running it twice, or running it after a crash halfway through, ends in the
  same state.

### Separate Before Serializing Shared State
* If they do not need the same mutable thing, give each its own.
* If they do, allow one writer, and enforce that in the structure.

# Then Make it Right

## Fix Root Causes
* Reproduce it.
* Fix the cause.
* A guard that only hides the crash is not a fix.

## Sequence work into verifiable units
* Finish one small unit and check it.
* Then start the next.

## Test Behavior, Not Implementation
* The test calls the code the way its user does and checks the result that user
  would see.
* If the test would still pass when every function returned nothing, throw it
  out.

## Crapper
* Use the crapper tool
* Reduce each function under CRAP 10 by splitting it, by testing it, or both.
* Consider whether case statements are worth reducing.

## Dryer
* Use the dryer tool to eliminate duplication that rank 0.8 or above.

## Mutator
* Use the mutator tool
* Cover the uncovered.
* Kill the survivors.
* Delete dead code.

## Refactoring
* Pin what the code does.
* Change the structure.
* Prove the behavior did not change.

# Practice

## Keep a Log
* Keep a log of every action you take and the reason you took it.
* Report that log upon completion.

## Guard the Context Window
* Keep the main thread small.
* Send the bulk elsewhere, and keep the summary.

## Worktree Cleanup
* Find what is safe to remove, confirm nothing still in use needs it, then
  reclaim the disk.
* Uncommitted work waits for a decision.

## Commit and Push
* Commit often, in small ordered commits.
* Each commit says why, what changed, and how you proved it.
* Push to the main line at the end.
```
