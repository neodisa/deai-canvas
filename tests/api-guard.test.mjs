import assert from "node:assert/strict";
import test from "node:test";

import { apiProblem } from "../app/api-guard.js";

/* Чужий процес на порту канваса — не гіпотеза: у власника двічі піднімався
   сторонній `python -m http.server 8765`, IPv6-сокет вигравав у `localhost`, і
   застосунок отримував 404-HTML замість своїх JSON. Далі він рапортував
   «tasks.json не читається» і «граф не завантажився» — тобто вказував на СВОЇ
   файли, хоча `tasks.json` валідний. Дизайнер за таким повідомленням іде
   чинити невинний файл. */

test("HTML з кодом 200 на /api/* — це чужий сервер, а не побитий файл", () => {
  assert.equal(apiProblem({ ok: true, status: 200, contentType: "text/html;charset=utf-8" }),
    "tasksErrPort");
});

test("відповідь зовсім без типу теж не наша", () => {
  /* `_send_json` у serve.py ставить `application/json` ЗАВЖДИ, тож відсутній
     тип означає, що відповідав не канвас. Правило строге навмисно: м'якше
     («немає типу — вважаємо своїм») повернуло б рівно ту неправду, проти якої
     ця перевірка й існує. */
  assert.equal(apiProblem({ ok: true, status: 200, contentType: null }), "tasksErrPort");
});

test("наш JSON проходить — і з параметрами типу теж", () => {
  assert.equal(apiProblem({ ok: true, status: 200, contentType: "application/json" }), null);
  assert.equal(apiProblem({ ok: true, status: 200,
                            contentType: "application/json; charset=utf-8" }), null);
  assert.equal(apiProblem({ ok: true, status: 200, contentType: "APPLICATION/JSON" }), null);
});

test("чесний збій нашого сервера лишається збоєм сервера, а не «зайнятим портом»", () => {
  /* 500 із нашого боку приходить текстом (`send_error`), і назвати його
     «порт зайнятий» означало б підмінити одну неправдиву підказку іншою:
     дизайнер пішов би дивитись `lsof` там, де впав наш обробник. Не-ok
     відповіді розбирає гілка, що була тут і до цієї перевірки. */
  assert.equal(apiProblem({ ok: false, status: 500, contentType: "text/html" }), null);
  assert.equal(apiProblem({ ok: false, status: 404, contentType: null }), null);
});
