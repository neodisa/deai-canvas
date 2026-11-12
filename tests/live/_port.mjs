import { randomInt } from "node:crypto";
import net from "node:net";

/** Чи вільний порт на 127.0.0.1 (туди ж біндиться `serve.py`): пробний listen і одразу close. */
function canBind(port) {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.once("error", () => resolve(false));
    s.listen(port, "127.0.0.1", () => s.close(() => resolve(true)));
  });
}

/**
 * Вільний порт зі смуги `portBase…portBase+99` (смуга — як і раніше, її неперетин між файлами стереже `tests/live-ports.test.mjs`).
 * Старт — випадковий, далі по колу. Не `hrtime % 100`: на Apple Silicon це лише 12 значень, і другий сервер файла сідав на порт живого першого
 * (`tests/live-port-pick.test.mjs`).
 */
export async function freePort(portBase) {
  const start = randomInt(100);
  for (let i = 0; i < 100; i += 1) {
    const port = portBase + ((start + i) % 100);
    if (await canBind(port)) return port;
  }
  throw new Error(`немає вільного порту в смузі ${portBase}…${portBase + 99}`);
}
