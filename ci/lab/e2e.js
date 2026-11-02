// Teste de ponta a ponta do Painel DevOps: abre o painel num navegador e usa TUDO como o aluno
// (modelos, botões, criação no Jenkins/Docker/Git/Ansible/Terraform/Python), anotando cada erro.
// Uso: node e2e.js <pasta-de-resultados>     (painel em http://localhost:8090)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT = process.argv[2] || 'resultado';
fs.mkdirSync(OUT, { recursive: true });
const URL = 'http://localhost:8090/';
const REPO = process.env.LAB_REPO || 'https://github.com/gabryelcetto/VM-de-devops.git';
const BRANCH = process.env.LAB_BRANCH || 'main';

const linhas = [];
const apiErros = [];
let falhas = 0, oks = 0;
function reg(secao, passo, ok, det) {
  const d = (det || '').toString().replace(/\s+/g, ' ').trim().slice(0, 600);
  const l = `${ok ? '[OK]   ' : '[FALHA]'} ${secao} :: ${passo}${d ? ' — ' + d : ''}`;
  ok ? oks++ : falhas++;
  linhas.push(l);
  console.log(l);
}
const dormir = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const nav = await chromium.launch();
  const ctx = await nav.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on('pageerror', e => reg('JavaScript', 'erro na página', false, e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) reg('JavaScript', 'console.error', false, m.text()); });
  page.on('response', async r => {
    if (r.url().includes('/api/') && r.status() >= 400) {
      let b = ''; try { b = await r.text(); } catch (e) {}
      apiErros.push({ quando: new Date().toISOString(), url: r.url(), status: r.status(), pedido: r.request().postData(), resposta: b });
    }
  });
  page.on('dialog', d => d.accept());

  // ------------------------------------------------------------------ ajudantes
  const aba = async nome => { await page.click(`#menu button[data-aba="${nome}"]`); await page.waitForTimeout(1800); };
  const limparAvisos = () => page.evaluate(() => { document.getElementById('avisos').innerHTML = ''; });
  const avisos = () => page.$$eval('#avisos .toast', ts => ts.map(t => ({ texto: t.textContent, erro: t.classList.contains('erro') })));
  const fechar = async () => { await page.evaluate(() => fecharModal()); await page.waitForTimeout(400); };
  const print = nome => page.screenshot({ path: path.join(OUT, nome + '.png'), fullPage: true }).catch(() => {});
  async function esperarAviso(timeout = 120000) {
    try { await page.waitForSelector('#avisos .toast', { timeout }); } catch (e) { return { texto: '(nenhum aviso apareceu)', erro: true }; }
    await page.waitForTimeout(300);
    const t = await avisos(); return t.find(x => x.erro) || t[0];
  }
  async function preencher(campos) {
    for (const [id, v] of Object.entries(campos || {})) {
      const el = await page.$('#a-' + id); if (!el) continue;
      const tipo = await el.evaluate(e => e.tagName + ':' + (e.type || ''));
      if (tipo === 'INPUT:checkbox') { if ((await el.isChecked()) !== !!v) await el.click(); }
      else if (tipo.startsWith('SELECT')) await el.selectOption({ label: v });
      else await el.fill(String(v));
    }
  }
  // abre um assistente, escolhe o modelo i, ajusta campos e clica no botão principal
  async function usarModelo(abrirJs, i, campos) {
    await limparAvisos();
    await page.evaluate(abrirJs);
    await page.waitForSelector(`#modal.aberto .modelo[data-i="${i}"]`, { timeout: 30000 });
    await page.click(`#modal .modelo[data-i="${i}"]`);
    await preencher(campos);
    await page.click('#m-rod button.pri');
  }
  const api = (url, dados) => page.evaluate(async ([u, d]) => { try { return { ok: true, r: await post(u, d) }; } catch (e) { return { ok: false, r: e.message }; } }, [url, dados]);
  const apiGet = url => page.evaluate(async u => { try { return await get(u); } catch (e) { return { erro: e.message }; } }, url);
  async function esperarConsole(timeout = 600000) {
    try {
      await page.waitForSelector('#c-estado', { timeout: 30000 });
      await page.waitForFunction(() => /conclu[íi]do|terminou com erro/i.test(document.getElementById('c-estado')?.textContent || ''), null, { timeout });
      const estado = await page.textContent('#c-estado'); const saida = await page.textContent('#c-saida');
      return { ok: /conclu[íi]do/i.test(estado), estado, saida };
    } catch (e) { return { ok: false, estado: 'não terminou: ' + e.message, saida: (await page.textContent('#c-saida').catch(() => '')) || '' }; }
  }
  async function esperarBuild(timeout = 300000) {
    try {
      await page.waitForFunction(() => /Finished: (SUCCESS|FAILURE|ABORTED|UNSTABLE)/.test(document.getElementById('b-saida')?.textContent || ''), null, { timeout });
      const s = await page.textContent('#b-saida'); return { ok: s.includes('Finished: SUCCESS'), saida: s };
    } catch (e) { return { ok: false, saida: 'build não terminou: ' + ((await page.textContent('#b-saida').catch(() => '')) || '').slice(-800) }; }
  }
  const fim = t => (t || '').slice(-500);
  const passo = async (secao, nome, fn) => { try { await fn(); } catch (e) { reg(secao, nome, false, 'exceção no teste: ' + e.message); await print('excecao-' + secao + '-' + nome.replace(/\W+/g, '_')); await fechar().catch(() => {}); } };

  await page.goto(URL);
  await page.waitForSelector('#menu');

  // ------------------------------------------------------------------ 1. todas as abas abrem
  for (const a of ['inicio', 'docker', 'jenkins', 'git', 'vscode', 'ansible', 'terraform', 'python', 'atividades', 'sistema']) {
    await passo('Abas', a, async () => {
      await aba(a); await page.waitForTimeout(1500);
      const at = await page.textContent('#atualizado');
      reg('Abas', `abre "${a}"`, !at.startsWith('Erro'), at);
      await print('aba-' + a);
    });
  }

  // ------------------------------------------------------------------ 2. Git
  await aba('git');
  await passo('Git', 'identidade', async () => {
    await limparAvisos(); await page.evaluate(() => gitIdent());
    await page.fill('#g-nome', 'Aluno Lab'); await page.fill('#g-email', 'aluno@lab.local'); await page.click('#m-rod button.pri');
    const a = await esperarAviso(20000); reg('Git', 'configurar nome e e-mail', !a.erro, a.texto);
  });
  await passo('Git', 'chave', async () => {
    await limparAvisos(); await page.evaluate(() => gerarChave(false)); await page.click('#m-rod button.pri');
    const a = await esperarAviso(30000); reg('Git', 'gerar chave SSH', !a.erro, a.texto);
  });
  const nomesRepo = ['lab-repo-py', 'lab-repo-tf', 'lab-repo-node', 'lab-repo-simples'];
  for (let i = 0; i < 4; i++) {
    await passo('Git', 'novo repo ' + i, async () => {
      await usarModelo(() => novoRepo(), i, { nome: nomesRepo[i], vscode: false });
      const a = await esperarAviso(30000); reg('Git', `novo repositório (modelo ${i})`, !a.erro, a.texto); await fechar();
    });
  }
  await passo('Git', 'commit pela tela', async () => {
    await aba('git');
    const idx = await page.evaluate(() => DADOS.git.repos.findIndex(r => r.nome === 'lab-repo-py'));
    await api('/api/arquivo', { acao: 'salvar', caminho: '/home/aluno/projetos/lab-repo-py/app.py', conteudo: 'print("ola")\n' });
    await aba('git');
    await limparAvisos(); await page.evaluate(i => gitCommit(i), idx);
    await page.fill('#c-msg', 'primeiro commit do laboratorio'); await page.click('#m-rod button.pri');
    const a = await esperarAviso(20000); reg('Git', 'commit pela tela (arquivos marcados)', !a.erro, a.texto); await fechar();
  });
  const R = '/home/aluno/projetos/lab-repo-py';
  for (const [nome, d, ok] of [
    ['criar e trocar de branch', { acao: 'checkout', repo: R, branch: 'feature/teste' }, true],
    ['commit na branch', null, true],
    ['voltar para main', { acao: 'checkout', repo: R, branch: 'main' }, true],
    ['merge da branch', { acao: 'merge', repo: R, branch: 'feature/teste' }, true],
    ['tag', { acao: 'tag', repo: R, tag: 'v1.0.0' }, true],
    ['gráfico', { acao: 'grafico', repo: R }, true],
    ['info do repositório', { acao: 'info_repo', repo: R }, true],
    ['remoto', { acao: 'remoto', repo: R, url: 'https://github.com/usuario/repositorio.git' }, true],
    ['diff', { acao: 'diff', repo: R }, true],
    ['desfazer último commit', { acao: 'desfazer_commit', repo: R }, true],
    ['stash', { acao: 'stash', repo: R }, true],
    ['stash pop', { acao: 'stash_pop', repo: R }, true],
    ['apagar branch não juntada: avisa antes', { acao: 'apagar_branch', repo: R, branch: 'feature/teste' }, false],
    ['apagar branch (forçado, depois do aviso)', { acao: 'apagar_branch', repo: R, branch: 'feature/teste', forcar: true }, true],
  ]) {
    await passo('Git', nome, async () => {
      if (!d) {
        await api('/api/arquivo', { acao: 'salvar', caminho: R + '/branch.txt', conteudo: 'feito na branch\n' });
        const r = await api('/api/git', { acao: 'commit', repo: R, mensagem: 'commit na branch', arquivos: ['branch.txt'] });
        return reg('Git', nome, r.ok, r.r);
      }
      const r = await api('/api/git', d); reg('Git', nome, r.ok === ok, typeof r.r === 'string' ? r.r : JSON.stringify(r.r));
    });
  }
  await passo('QA', 'push sem commit', async () => {
    await usarModelo(() => novoRepo(), 3, { nome: 'qa-vazio', vscode: false, remoto: 'https://github.com/gabryelcetto/nao-existe-qa.git' });
    await esperarAviso(20000); await fechar();
    await page.evaluate(() => executar({ ferramenta: 'git', acao: 'push', repo: '/home/aluno/projetos/qa-vazio' }));
    const c = await esperarConsole(120000);
    reg('QA', 'Push sem nenhum commit explica o que fazer', !c.ok && /Dica: Ainda não existe nenhum commit/.test(c.saida), fim(c.saida)); await fechar();
  });
  await aba('git'); await print('git-depois');

  // ------------------------------------------------------------------ 3. Jenkins
  await aba('jenkins');
  await passo('Jenkins', 'caso do aluno', async () => {
    // exatamente o que o aluno fez: Pipeline: Olá, nome ola-jenkins, sem construir
    await usarModelo(() => novoItemJenkins(), 0, { nome: 'ola-jenkins', construir: false });
    const a = await esperarAviso(60000); reg('Jenkins', 'Pipeline: Olá (ola-jenkins, sem construir) — caso do aluno', !a.erro, a.texto);
    await fechar();
    await usarModelo(() => novoItemJenkins(), 0, { nome: 'ola-jenkins', construir: false });
    const b = await esperarAviso(60000);
    reg('Jenkins', 'criar de novo com o mesmo nome dá mensagem clara', b.erro && /Já existe um item/.test(b.texto), b.texto);
    await fechar();
  });
  const modelosJk = await page.evaluate(() => TIPOS_JENKINS.map(m => ({ nome: m.nome, tipo: m.valores.tipo })));
  const resultadoEsperado = { 'Pipeline: Docker Compose': true };
  for (let i = 0; i < modelosJk.length; i++) {
    const m = modelosJk[i];
    await passo('Jenkins', m.nome, async () => {
      const nome = 'lab-' + i;
      const campos = { nome };
      if (['pipeline_scm', 'freestyle', 'multibranch'].includes(m.tipo) && /Git|Multibranch/.test(m.nome)) Object.assign(campos, { repo: REPO, branch: BRANCH, jenkinsfile: 'exemplos/Jenkinsfile' });
      await usarModelo(() => novoItemJenkins(), i, campos);
      const a = await esperarAviso(90000);
      reg('Jenkins', `criar "${m.nome}"`, !a.erro, a.texto);
      if (!a.erro && ['pipeline', 'pipeline_scm', 'freestyle'].includes(m.tipo)) {
        const b = await esperarBuild(360000);
        reg('Jenkins', `build de "${m.nome}" termina com sucesso`, b.ok, fim(b.saida));
        await print('jenkins-build-' + i);
      }
      await fechar();
    });
  }
  await passo('Jenkins', 'item dentro de pasta', async () => {
    await usarModelo(() => novoItemJenkins('lab-9'), 6, { nome: 'dentro-da-pasta' });
    const a = await esperarAviso(60000); reg('Jenkins', 'Freestyle dentro da Pasta', !a.erro, a.texto);
    const b = await esperarBuild(240000); reg('Jenkins', 'build dentro da Pasta', b.ok, fim(b.saida)); await fechar();
  });
  await passo('Jenkins', 'container do pipeline fica ligado', async () => {
    const d = await apiGet('/api/docker');
    const c = (d.containers || []).find(x => x.nome === 'site-jenkins');
    reg('Jenkins', 'container criado pelo "Pipeline: Docker" continua ligado e aparece no Docker', c && c.estado === 'running' && c.origem === 'jenkins', c ? `${c.estado} origem=${c.origem} limite=${c.limite_memoria}` : 'não apareceu');
    reg('Jenkins', 'limite de 1 GB aplicado ao container do pipeline', c && c.limite_memoria === 1073741824, c ? String(c.limite_memoria) : '');
  });
  await passo('QA', 'endereço de exemplo falso', async () => {
    await usarModelo(() => novoItemJenkins(), 5, { nome: 'qa-falso', repo: 'https://github.com/usuario/repositorio.git', construir: false });
    const a = await esperarAviso(30000); reg('QA', 'Jenkins recusa o endereço de exemplo usuario/repositorio com explicação', a.erro && /Troque o endereço/.test(a.texto), a.texto); await fechar();
  });
  await passo('QA', 'modelos do Git vêm com exemplo real', async () => {
    const r = await page.evaluate(() => TIPOS_JENKINS.filter(m => m.valores.repo).map(m => m.valores.repo));
    reg('QA', 'nenhum modelo do Jenkins vem com repositório falso', r.length > 0 && r.every(u => !/usuario\/repositorio/.test(u)), r.join(' '));
  });
  await passo('QA', 'cópia constrói', async () => {
    await api('/api/jenkins', { acao: 'copiar', job: 'lab-0', novo: 'lab-0-qa-copia' });
    const c = await api('/api/jenkins', { acao: 'construir', job: 'lab-0-qa-copia' });
    let ok = false, txt = '';
    for (let i = 0; i < 40 && !ok; i++) { await dormir(3000); const k = await api('/api/jenkins', { acao: 'console', job: 'lab-0-qa-copia' }); txt = k.r || ''; ok = /Finished: SUCCESS/.test(txt); }
    reg('QA', 'job copiado constrói de verdade (não fica preso esperando salvar)', ok, (c.r || '') + ' ' + fim(txt));
    await api('/api/jenkins', { acao: 'apagar', job: 'lab-0-qa-copia' });
  });
  await passo('QA', 'credencial vazia', async () => {
    const r = await api('/api/jenkins', { acao: 'criar_credencial', tipo: 'usuario', id: 'qa-vazia', usuario: '', senha: '' });
    reg('QA', 'credencial de token vazia é recusada com explicação', !r.ok && /Preencha/.test(r.r), r.r);
    const r2 = await api('/api/jenkins', { acao: 'criar_credencial', tipo: 'usuario', id: 'qa-senha', usuario: 'aluno', senha: 'minhasenha123' });
    reg('QA', 'senha da conta no lugar do token é recusada com explicação', !r2.ok && /token do GitHub/.test(r2.r), r2.r);
  });
  await passo('QA', 'parâmetros', async () => {
    const p = await api('/api/jenkins', { acao: 'parametros', job: 'lab-4' });
    reg('QA', 'Painel lê os parâmetros do job', p.ok && (p.r.parametros || []).length === 2, JSON.stringify(p.r).slice(0, 200));
    await api('/api/jenkins', { acao: 'construir', job: 'lab-4', parametros: { NOME: 'qa', AMBIENTE: 'producao' } });
    let txt = '';
    for (let i = 0; i < 40; i++) { await dormir(3000); const k = await api('/api/jenkins', { acao: 'console', job: 'lab-4' }); txt = k.r || ''; if (/Ola, qa! Publicando em producao/.test(txt) && /Finished/.test(txt)) break; }
    reg('QA', 'build com os valores escolhidos (NOME=qa, AMBIENTE=producao)', /Ola, qa! Publicando em producao/.test(txt), fim(txt));
  });
  await passo('QA', 'tela de parâmetros', async () => {
    await aba('jenkins'); await limparAvisos();
    await page.evaluate(() => jkConstruir('lab-4'));
    await page.waitForSelector('#modal [data-p="AMBIENTE"]', { timeout: 20000 });
    reg('QA', 'Construir num job com parâmetros abre a tela para escolher os valores', true, '');
    await print('qa-parametros'); await fechar();
  });
  await passo('QA', 'compose do Jenkins na aba Compose', async () => {
    const d = await apiGet('/api/docker');
    const p = (d.projetos || []).find(x => x.nome === 'site-jenkins');
    reg('QA', 'projeto Compose criado pelo Jenkins aparece', !!p, JSON.stringify(p || {}));
    await page.evaluate(() => { SUB.docker = 'compose'; }); await aba('docker'); await page.waitForTimeout(1500); await print('qa-compose-jenkins');
    const temEtq = await page.evaluate(() => document.querySelector('#docker')?.textContent.includes('Criado pelo Jenkins'));
    reg('QA', 'aba Compose marca o projeto como "Criado pelo Jenkins"', temEtq, '');
    const r = await api('/api/executar', { ferramenta: 'docker', acao: 'compose_down_projeto', projeto: 'site-jenkins' });
    const t = r.ok ? await page.evaluate(id => new Promise(res => { const v = async () => { const x = await get('/api/tarefa?id=' + id); if (x.fim) return res(x); setTimeout(v, 800); }; v(); }), r.r.tarefa) : null;
    reg('QA', 'Derrubar o projeto do Jenkins pelo Painel funciona', t && t.codigo === 0, t ? t.linhas.join(' ').slice(-300) : r.r);
    await page.evaluate(() => { SUB.docker = 'containers'; });
  });
  // credenciais (4 modelos)
  const chaveOutra = fs.existsSync('/tmp/lab-chave') ? fs.readFileSync('/tmp/lab-chave', 'utf8') : '';
  for (const [i, campos] of [[0, { id: 'lab-token', usuario: 'aluno', senha: 'ghp_teste123' }], [1, { id: 'lab-ssh-minha' }], [2, { id: 'lab-ssh-outra', chave: chaveOutra }], [3, { id: 'lab-segredo', segredo: 's3gr3do' }]]) {
    await passo('Jenkins', 'credencial ' + i, async () => {
      await usarModelo(() => credenciais(), i, campos);
      const a = await esperarAviso(30000); reg('Jenkins', `credencial (modelo ${i})`, !a.erro, a.texto); await page.waitForTimeout(800); await fechar();
    });
  }
  // ações nos jobs
  const J = 'lab-0';
  for (const [nome, d] of [
    ['ver configuração', { acao: 'ver_config', job: J }],
    ['editar script', { acao: 'salvar_config', job: J, valor: "pipeline {\n  agent any\n  stages {\n    stage('Editado') {\n      steps { echo 'editado pelo painel' }\n    }\n  }\n}\n" }],
    ['gatilhos', { acao: 'salvar_config', job: J, cron: 'H 8 * * 1-5', cron_scm: '' }],
    ['desligar gatilhos', { acao: 'salvar_config', job: J, cron: '', cron_scm: '' }],
    ['desativar', { acao: 'desativar', job: J }],
    ['ativar', { acao: 'ativar', job: J }],
    ['copiar', { acao: 'copiar', job: J, novo: 'lab-0-copia' }],
    ['construir', { acao: 'construir', job: J }],
    ['etapas', { acao: 'etapas', job: J }],
    ['console', { acao: 'console', job: J }],
    ['apagar cópia', { acao: 'apagar', job: 'lab-0-copia' }],
    ['credenciais (lista)', { acao: 'credenciais' }],
  ]) {
    await passo('Jenkins', nome, async () => { const r = await api('/api/jenkins', d); reg('Jenkins', nome, r.ok, typeof r.r === 'string' ? r.r.slice(-300) : JSON.stringify(r.r).slice(0, 300)); await dormir(800); });
  }
  await aba('jenkins'); await print('jenkins-depois');

  // ------------------------------------------------------------------ 4. Docker
  await aba('docker');
  const modelosDk = await page.evaluate(() => MODELOS_CONTAINER.map(m => m.nome));
  for (let i = 0; i < modelosDk.length; i++) {
    const m = modelosDk[i];
    await passo('Docker', m, async () => {
      const campos = m === 'Personalizado' ? { imagem: 'python:3.12-slim', nome: 'iw' } : m === 'Hello World' ? { nome: 'lab-hello' } : {};
      await usarModelo(() => novoContainer(), i, campos);
      const a = await esperarAviso(300000);
      reg('Docker', `criar container "${m}"`, !a.erro, a.texto);
      await fechar(); await dormir(8000);
      const d = await apiGet('/api/docker');
      const nome = campos.nome || (await page.evaluate(i => MODELOS_CONTAINER[i].valores.nome, i));
      const c = (d.containers || []).find(x => x.nome === nome);
      if (m !== 'Hello World') reg('Docker', `"${m}" continua rodando depois de 8 s`, c && c.estado === 'running', c ? `${c.estado} — ${c.status}` : 'container não encontrado');
      if (c) reg('Docker', `"${m}" sem rótulo de compose estranho`, !/^</.test(c.projeto || ''), 'projeto=' + c.projeto);
    });
  }
  await aba('docker'); await print('docker-containers');
  for (const [nome, d] of [
    ['parar', { acao: 'stop', container: 'meu-site' }], ['iniciar', { acao: 'start', container: 'meu-site' }], ['reiniciar', { acao: 'restart', container: 'meu-site' }],
    ['logs', { acao: 'logs', container: 'meu-site' }], ['detalhes', { acao: 'inspecionar', container: 'meu-site' }],
    ['rodar comando', { acao: 'exec', container: 'meu-site', comando: 'nginx -v' }],
    ['criar rede', { acao: 'rede_criar', nome: 'lab-rede' }], ['apagar rede', { acao: 'rede_rm', nome: 'lab-rede' }],
    ['criar volume', { acao: 'volume_criar', nome: 'lab-volume' }], ['apagar volume', { acao: 'volume_rm', nome: 'lab-volume' }],
  ]) {
    await passo('Docker', nome, async () => { const r = await api('/api/docker', d); reg('Docker', nome, r.ok, typeof r.r === 'string' ? r.r.slice(-300) : JSON.stringify(r.r).slice(0, 300)); });
  }
  await passo('Docker', 'site responde', async () => {
    const r = await page.evaluate(async () => { try { const x = await fetch('http://localhost:8081', { mode: 'no-cors' }); return 'ok'; } catch (e) { return e.message; } });
    reg('Docker', 'site do Nginx responde em :8081', r === 'ok', r);
  });
  // remover containers dos modelos (libera portas para o Compose)
  for (const n of ['meu-site', 'meu-apache', 'meu-python', 'meu-mysql', 'meu-postgres', 'meu-redis', 'meu-ubuntu', 'lab-hello', 'iw']) await api('/api/docker', { acao: 'rm', container: n });
  const modelosCompose = await page.evaluate(() => MODELOS_COMPOSE.map(m => m.nome));
  for (let i = 0; i < modelosCompose.length; i++) {
    await passo('Docker', 'compose ' + i, async () => {
      await usarModelo(() => novoCompose(), i, { nome: 'lab-compose-' + i });
      const c = await esperarConsole(600000);
      reg('Docker', `Compose "${modelosCompose[i]}" sobe`, c.ok, c.estado + ' ' + fim(c.saida)); await print('compose-' + i); await fechar();
      const down = await api('/api/executar', { ferramenta: 'docker', acao: 'compose_down', arquivo: `/home/aluno/projetos/lab-compose-${i}/docker-compose.yml` });
      reg('Docker', `Compose "${modelosCompose[i]}" derruba`, down.ok, JSON.stringify(down.r).slice(0, 200)); await dormir(15000);
    });
  }
  for (let i = 0; i < 2; i++) {
    await passo('Docker', 'imagem ' + i, async () => {
      await usarModelo(() => novaImagem(), i, { nome: 'lab-imagem-' + i });
      const c = await esperarConsole(600000); reg('Docker', `construir imagem (modelo ${i})`, c.ok, c.estado + ' ' + fim(c.saida)); await fechar();
    });
  }
  await passo('QA', 'container de imagem própria', async () => {
    const sug = await api('/api/docker', { acao: 'sugestao', imagem: 'lab-imagem-0' });
    reg('QA', 'criar container de uma imagem com site já sugere porta e nome', sug.ok && /^81\d\d:80$/.test(sug.r.portas || ''), JSON.stringify(sug.r));
    await limparAvisos(); await page.evaluate(() => novoContainer('lab-imagem-0')); await page.waitForTimeout(1500);
    const portas = await page.inputValue('#a-portas'); await page.click('#m-rod button.pri');
    const a = await esperarAviso(120000); reg('QA', 'container da imagem própria sobe', !a.erro, a.texto); await fechar(); await dormir(2000);
    const ok = await page.evaluate(async p => { try { await fetch('http://localhost:' + p, { mode: 'no-cors' }); return 'ok'; } catch (e) { return e.message; } }, portas.split(':')[0]);
    reg('QA', 'site da imagem própria abre na porta sugerida (' + portas + ')', ok === 'ok', ok);
  });
  await passo('QA', 'script de uma vez só', async () => {
    await limparAvisos(); await page.evaluate(() => novoContainer('lab-imagem-1')); await page.waitForTimeout(1500); await page.click('#m-rod button.pri');
    const a = await esperarAviso(120000);
    reg('QA', 'imagem de script que termina com sucesso não aparece como erro', !a.erro && /terminou com sucesso/.test(a.texto), a.texto);
    await fechar();
  });
  await passo('QA', 'nome repetido no Docker', async () => {
    await api('/api/docker', { acao: 'run', imagem: 'nginx:alpine', nome: 'qa-dup', memoria: '128m' });
    const r = await api('/api/docker', { acao: 'run', imagem: 'nginx:alpine', nome: 'qa-dup', memoria: '128m' });
    reg('QA', 'container com nome repetido dá mensagem clara', !r.ok && /Já existe um container chamado qa-dup/.test(r.r), r.r);
    await api('/api/docker', { acao: 'rm', container: 'qa-dup' });
  });
  await passo('QA', 'portas dos modelos', async () => {
    const usadas = await page.evaluate(() => [...MODELOS_CONTAINER.map(m => (m.valores.portas || '').split(':')[0]), ...MODELOS_COMPOSE.flatMap(m => [...m.valores.conteudo.matchAll(/"(\d+):\d+"/g)].map(x => x[1])), '8080', '8087', '8088', '8090'].filter(Boolean));
    const rep = usadas.filter((p, i) => usadas.indexOf(p) !== i);
    reg('QA', 'modelos de container/Compose/Jenkins não usam a mesma porta', !rep.length, 'repetidas: ' + rep.join(','));
  });
  await passo('Docker', 'baixar imagem', async () => {
    await limparAvisos(); await page.evaluate(() => baixarImagem()); await page.fill('#bx-img', 'alpine:latest'); await page.click('#m-rod button.pri');
    const c = await esperarConsole(300000); reg('Docker', 'baixar imagem', c.ok, c.estado); await fechar();
  });
  await aba('docker'); await print('docker-depois');

  // ------------------------------------------------------------------ 5. Ansible
  await aba('ansible');
  const modelosAn = await page.evaluate(() => MODELOS_ANSIBLE.map(m => m.nome));
  for (let i = 0; i < modelosAn.length; i++) {
    await passo('Ansible', modelosAn[i], async () => {
      await usarModelo(() => novoPlaybook(), i, { nome: 'lab-ansible-' + i });
      const c = await esperarConsole(300000); reg('Ansible', `playbook "${modelosAn[i]}" roda`, c.ok, c.estado + ' ' + fim(c.saida)); await fechar();
    });
  }
  await passo('Ansible', 'comando rápido', async () => {
    await page.evaluate(() => adhoc()); await page.click('#m-rod button.pri');
    const c = await esperarConsole(120000); reg('Ansible', 'comando rápido (ping)', c.ok, c.estado + ' ' + fim(c.saida)); await fechar();
  });
  for (const ac of ['simular', 'checar']) {
    await passo('Ansible', ac, async () => {
      const r = await api('/api/executar', { ferramenta: 'ansible', acao: ac, playbook: '/home/aluno/projetos/lab-ansible-0/playbook.yml' });
      reg('Ansible', ac, r.ok, JSON.stringify(r.r).slice(0, 200));
    });
  }
  await passo('QA', 'ansible com inventário', async () => {
    await api('/api/arquivo', { acao: 'salvar', caminho: '/home/aluno/projetos/lab-ansible-0/inventario.ini', conteudo: '[local]\nlocalhost ansible_connection=local\n' });
    await page.evaluate(() => executar({ ferramenta: 'ansible', acao: 'rodar', playbook: '/home/aluno/projetos/lab-ansible-0/playbook.yml' }));
    const c = await esperarConsole(180000);
    reg('QA', 'playbook com inventário próprio usa o inventário e roda', c.ok && !/-c local/.test(c.estado), c.estado + ' ' + fim(c.saida)); await fechar();
  });
  await aba('ansible'); await print('ansible-depois');

  // ------------------------------------------------------------------ 6. Terraform
  await aba('terraform');
  const modelosTf = await page.evaluate(() => MODELOS_TF.map(m => m.nome));
  for (let i = 0; i < modelosTf.length; i++) {
    await passo('Terraform', modelosTf[i], async () => {
      await usarModelo(() => novoTerraform(), i, { nome: 'lab-tf-' + i });
      const c = await esperarConsole(300000); reg('Terraform', `init "${modelosTf[i]}"`, c.ok, c.estado + ' ' + fim(c.saida)); await fechar();
      for (const ac of ['validate', 'plan', 'apply', 'output', 'show', 'destroy']) {
        await limparAvisos();
        await page.evaluate(([p, a]) => executar({ ferramenta: 'terraform', acao: a, pasta: p }), ['/home/aluno/projetos/lab-tf-' + i, ac]);
        const k = await esperarConsole(300000); reg('Terraform', `${ac} "${modelosTf[i]}"`, k.ok, k.estado + ' ' + fim(k.saida)); await fechar();
      }
    });
  }
  await aba('terraform'); await print('terraform-depois');

  // ------------------------------------------------------------------ 7. Python
  await aba('python');
  const modelosPy = await page.evaluate(() => MODELOS_PY.map(m => [m.nome, m.valores.arquivo]));
  for (let i = 0; i < modelosPy.length; i++) {
    const [nomeM, arq] = modelosPy[i];
    await passo('Python', nomeM, async () => {
      await usarModelo(() => novoPython(), i, { nome: 'lab-py-' + i });
      const c = await esperarConsole(300000); reg('Python', `criar .venv "${nomeM}"`, c.ok, c.estado + ' ' + fim(c.saida));
      await dormir(2000);
      // o pip roda logo depois (quando há pacotes): espera ele também
      const est = await page.textContent('#c-estado').catch(() => '');
      if (/pip/.test(est)) { const p = await esperarConsole(300000); reg('Python', `instalar pacotes "${nomeM}"`, p.ok, p.estado + ' ' + fim(p.saida)); }
      await fechar();
      if (nomeM !== 'API com Flask') {
        await page.evaluate(([p, s]) => executar({ ferramenta: 'python', acao: 'rodar', pasta: p, script: p + '/' + s }), ['/home/aluno/projetos/lab-py-' + i, arq]);
        const k = await esperarConsole(120000); reg('Python', `rodar ${arq}`, k.ok, k.estado + ' ' + fim(k.saida)); await fechar();
      }
    });
  }
  await passo('Python', 'pytest', async () => {
    await page.evaluate(() => executar({ ferramenta: 'python', acao: 'pytest', pasta: '/home/aluno/projetos/lab-py-2' }));
    const k = await esperarConsole(120000); reg('Python', 'rodar testes (pytest)', k.ok, k.estado + ' ' + fim(k.saida)); await fechar();
  });
  await aba('python'); await print('python-depois');

  // ------------------------------------------------------------------ 8. abas de novo, com tudo criado
  for (const a of ['inicio', 'vscode', 'atividades', 'sistema']) { await aba(a); await page.waitForTimeout(1500); const at = await page.textContent('#atualizado'); reg('Abas', `"${a}" com tudo criado`, !at.startsWith('Erro'), at); await print('final-' + a); }

  await passo('QA', 'desligar e ligar o Docker', async () => {
    const off = await api('/api/docker', { acao: 'desligar' });
    await dormir(3000); const s1 = await apiGet('/api/saude-lab');
    reg('QA', 'Desligar o Docker desliga de verdade', off.ok && s1.docker !== 'active', (off.r || '') + ' estado=' + s1.docker);
    const on = await api('/api/docker', { acao: 'ligar' }); await dormir(3000); const s2 = await apiGet('/api/saude-lab');
    reg('QA', 'Ligar o Docker de novo funciona', on.ok && s2.docker === 'active', (on.r || '') + ' estado=' + s2.docker);
  });
  await passo('QA', 'favorito e página inicial', async () => {
    const pag = fs.existsSync('../../files/gui/inicio.html') ? fs.readFileSync('../../files/gui/inicio.html', 'utf8') : '';
    reg('QA', 'página inicial do Lab tem o link do Painel DevOps', pag.includes('http://localhost:8090'), '');
  });

  // ------------------------------------------------------------------ relatório
  const txt = [`Laboratório do Painel — ${new Date().toISOString()}`, `Repositório de teste: ${REPO} (${BRANCH})`, `OK: ${oks}   FALHAS: ${falhas}`, '', ...linhas].join('\n');
  fs.writeFileSync(path.join(OUT, 'RELATORIO.txt'), txt + '\n');
  fs.writeFileSync(path.join(OUT, 'erros-api.json'), JSON.stringify(apiErros, null, 2));
  console.log(`\nOK: ${oks}   FALHAS: ${falhas}`);
  await nav.close();
})().catch(async e => { console.error('ERRO GERAL DO TESTE:', e); fs.writeFileSync(path.join(OUT, 'RELATORIO.txt'), ['ERRO GERAL: ' + e.stack, '', ...linhas].join('\n')); process.exit(0); });
