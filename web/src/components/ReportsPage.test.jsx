import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('../api/client', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  materializeReport: vi.fn(),
  unmaterializeReport: vi.fn(),
  refreshReport: vi.fn(),
}));
vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }));

import api from '../api/client';
import { useAuth } from '../context/AuthContext';
import ReportsPage from './ReportsPage';

const RELATORIOS = [
  { id: 1, name: 'Receita mensal', description: 'Receita por mês', view_name: 'vw_receita', sql_query: 'SELECT 1' },
  { id: 2, name: 'Inadimplência', description: '', view_name: 'vw_inadimplencia', sql_query: 'SELECT 2' },
];

function comPermissoes(perms) {
  useAuth.mockReturnValue({ hasPermission: (flag) => Boolean(perms[flag]) });
}

describe('ReportsPage', () => {
  beforeEach(() => {
    api.get.mockImplementation(async (url) => (
      url === '/reports' ? { data: { reports: RELATORIOS } } : { data: { functions: [] } }
    ));
  });
  afterEach(cleanup);

  it('lista as views e esconde a criação de quem não tem can_manage_views', async () => {
    comPermissoes({});
    render(<ReportsPage />);

    expect(await screen.findByText('Receita mensal')).toBeTruthy();
    expect(screen.getByText('Inadimplência')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Create View/ })).toBeNull();
    expect(screen.queryByTitle('Edit View')).toBeNull();
  });

  it('filtra a lista pelo nome da view no SQL', async () => {
    comPermissoes({});
    render(<ReportsPage />);
    await screen.findByText('Receita mensal');

    fireEvent.click(screen.getByTitle('Pesquisar'));
    fireEvent.change(screen.getByPlaceholderText('Pesquisar...'), { target: { value: 'VW_INAD' } });

    expect(screen.queryByText('Receita mensal')).toBeNull();
    expect(screen.getByText('Inadimplência')).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText('Pesquisar...'), { target: { value: 'nao-existe' } });
    expect(screen.getByText('Nenhuma view encontrada.')).toBeTruthy();
  });

  it('só salva a view depois que o SQL atual passou no teste', async () => {
    comPermissoes({ can_manage_views: true });
    api.post.mockResolvedValue({ data: {} });
    render(<ReportsPage />);
    await screen.findByText('Receita mensal');

    fireEvent.click(screen.getByRole('button', { name: /Create View/ }));
    fireEvent.change(screen.getByPlaceholderText('e.g., Quarterly Revenue'), { target: { value: 'Saldo' } });
    const sql = screen.getByPlaceholderText('SELECT * FROM table_name WHERE...');
    fireEvent.change(sql, { target: { value: 'SELECT saldo FROM contas' } });
    const salvar = screen.getByRole('button', { name: 'Save View' });
    expect(salvar.disabled).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: /Test Query/ }));
    await screen.findByText('Query verified successfully!');
    expect(api.post).toHaveBeenCalledWith('/query', { sql: 'SELECT saldo FROM contas' });
    expect(salvar.disabled).toBe(false);

    // SQL alterado depois do teste exige testar de novo
    fireEvent.change(sql, { target: { value: 'SELECT saldo, cliente FROM contas' } });
    expect(salvar.disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /Test Query/ }));
    await screen.findByText('Query verified successfully!');

    fireEvent.click(salvar);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/reports', {
      name: 'Saldo',
      description: '',
      sql_query: 'SELECT saldo, cliente FROM contas',
    }));
  });
});
