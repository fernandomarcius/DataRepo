"""Kit de plataforma do DataRepo — codigo VENDORIZADO em cada servico.

A fonte da verdade e o `kit/` do repositorio do api (DataRepo). O
datarepo-ingestion carrega uma copia identica em `kit/` (e `db.py`),
atualizada manualmente. Nao edite a copia do ingestion: a alteracao
some no proximo sync e, antes disso, faz os dois divergirem em regra de
seguranca (JWT, permissoes, nome de objeto).

Por que copiar em vez de publicar um pacote: um pacote privado exigiria
credencial de leitura em todo build de imagem e amarraria o release do
ingestion ao release do pacote. O kit e pequeno e muda pouco.
"""

KIT_VERSION = "1.0.0"
