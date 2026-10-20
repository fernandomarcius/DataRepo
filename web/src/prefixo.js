// Onde o app esta montado. O mesmo codigo e servido em varios lugares:
//  - na RAIZ de um host: nginx desta imagem (compose local), `vite dev`, testes;
//  - sob `/workloads/{tenant}/{servico}/` no plataforma, que publica todo workload num mesmo host
//    (platform.example.com) e separa um do outro pelo caminho;
//  - sob qualquer outro caminho de um proxy na frente dele (ex.: example.com/dataapp, por um
//    Worker do Cloudflare que repassa para o plataforma).
//
// Por isso nenhuma URL absoluta do app pode ser literal: `/api/v1/x` e `/logo.svg` escapariam do
// prefixo. A API sai de `prefixo()` (api/client.js), arquivo de `public/` sai de `rota()` e o
// `basename` do Router e `prefixo()`. Os assets do Vite nao passam por aqui: fora da raiz o build
// usa `VITE_BASE=./` (vite.config.js) e o nginx de la reescreve os caminhos relativos do index.html.
//
// So o NAVEGADOR conhece o prefixo: cada salto na frente (gateway da plataforma, Worker) tira o
// seu pedaco do caminho antes de repassar, e nenhum header o carrega. O prefixo sai da URL de onde
// o proprio bundle foi carregado (`import.meta.url`, `<prefixo>/assets/<arquivo>.js`), que o
// navegador resolveu contra a pagina: vale para qualquer caminho, sem lista de prefixos conhecidos.
const BUNDLE = /^(.*)\/assets\/[^/]+$/;
// `vite dev` serve os modulos em /src/...: ai vale a regra de caminho do gateway da plataforma.
const PREFIXO_WORKLOAD = /^\/workloads\/[^/]+\/[^/]+(?=\/|$)/;

/** `''` na raiz; `/workloads/acme/datarepo-web`, `/dataapp`... fora dela (sem barra no fim). */
export function prefixo(urlDoModulo = import.meta.url, pathname = window.location.pathname) {
    const doBundle = BUNDLE.exec(new URL(urlDoModulo).pathname);
    if (doBundle) return doBundle[1];
    return PREFIXO_WORKLOAD.exec(pathname)?.[0] ?? '';
}

/** Caminho do app (`/logo.svg`) -> URL que o navegador pode abrir, com o prefixo quando houver. */
export function rota(caminho) {
    const c = caminho.startsWith('/') ? caminho : `/${caminho}`;
    return `${prefixo()}${c}`;
}
