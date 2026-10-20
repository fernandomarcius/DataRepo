import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('../api/client', () => ({ default: { get: vi.fn() } }));

import api from '../api/client';
import VisualQueryBuilder from './VisualQueryBuilder';

const SCHEMA = [
  { column_name: 'regiao', data_type: 'text' },
  { column_name: 'valor', data_type: 'numeric' },
];

async function montarComTabela(onRun) {
  render(<VisualQueryBuilder tables={['vendas', 'clientes']} onRun={onRun} limit={100} setLimit={vi.fn()} />);
  fireEvent.change(screen.getByDisplayValue('-- Escolha uma tabela --'), { target: { value: 'vendas' } });
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/tables/vendas/schema'));
  // a seção "2. Selecione Colunas" (JOIN, HAVING e ordenação têm o próprio "Adicionar")
  const secao = screen.getByText('2. Selecione Colunas').closest('button').parentElement;
  const adicionar = within(secao).getByRole('button', { name: 'Adicionar' });
  await waitFor(() => expect(adicionar.disabled).toBe(false));
  return adicionar;
}

describe('VisualQueryBuilder', () => {
  beforeEach(() => {
    localStorage.clear();
    api.get.mockResolvedValue({ data: { schema: SCHEMA } });
  });
  afterEach(cleanup);

  it('executa SELECT * da tabela escolhida quando nada mais foi configurado', async () => {
    const onRun = vi.fn();
    await montarComTabela(onRun);

    fireEvent.click(screen.getByRole('button', { name: /Executar Consulta/ }));

    expect(onRun).toHaveBeenCalledWith('SELECT *\nFROM vendas');
  });

  it('agrupa pelas colunas sem agregação quando há uma agregação', async () => {
    const onRun = vi.fn();
    const adicionar = await montarComTabela(onRun);

    fireEvent.click(adicionar);
    fireEvent.change(screen.getByDisplayValue('Campo'), { target: { value: 'valor' } });
    fireEvent.change(screen.getByDisplayValue('Nenhum'), { target: { value: 'SUM' } });
    fireEvent.click(adicionar);
    fireEvent.change(screen.getByDisplayValue('Campo'), { target: { value: 'regiao' } });
    fireEvent.click(screen.getByRole('button', { name: /Executar Consulta/ }));

    expect(onRun).toHaveBeenCalledWith('SELECT SUM(valor) AS sum_valor, regiao\nFROM vendas\nGROUP BY regiao');
  });

  it('bloqueia a execução de BETWEEN sem o segundo valor', async () => {
    const onRun = vi.fn();
    await montarComTabela(onRun);

    fireEvent.click(screen.getByRole('button', { name: /Adicionar Filtro/ }));
    fireEvent.change(screen.getByDisplayValue('Selecione o campo...'), { target: { value: 'valor' } });
    fireEvent.change(screen.getByDisplayValue('Igual (=)'), { target: { value: 'BETWEEN' } });
    fireEvent.change(screen.getByPlaceholderText('Valor'), { target: { value: '10' } });

    expect(await screen.findByText('Filtro 1: BETWEEN requer dois valores')).toBeTruthy();
    const executar = screen.getByRole('button', { name: /Corrija os erros/ });
    expect(executar.disabled).toBe(true);
    fireEvent.click(executar);
    expect(onRun).not.toHaveBeenCalled();
  });
});
