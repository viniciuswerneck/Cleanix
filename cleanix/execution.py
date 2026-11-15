#!/usr/bin/env python3
"""Execução de comandos do sistema, com ou sem privilégios de administrador."""

from __future__ import annotations

import logging
import os
import subprocess
from collections import namedtuple

log = logging.getLogger(__name__)

# PATH usado quando o comando roda via pkexec (root não herda o ambiente).
SYSTEM_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
COMMAND_TIMEOUT = 600  # segundos

Result = namedtuple('Result', 'ok output error')


def friendly_error(text):
    """Traduz os erros mais comuns do pkexec para uma linguagem simples."""
    if not text:
        return ''
    if 'Not authorized' in text or 'dismissed' in text.lower():
        return ('A senha de administrador não foi informada.\n'
                'Nada foi alterado no sistema.')
    if 'No such file or directory' in text and 'bash' in text:
        return 'Não foi possível iniciar o shell do sistema.'
    return text


def execute_command(command, as_root=False, timeout=COMMAND_TIMEOUT):
    """Executa ``command`` num shell e devolve um ``Result``.

    Roda sempre em uma thread separada (quem chama cuida disso), nunca
    levanta exceção e registra tudo no log do Cleanix.

    ``as_root=True`` usa o ``pkexec``, que abre a janela gráfica de senha do
    sistema operacional.
    """
    if as_root:
        argv = ['pkexec', '/usr/bin/bash', '-c', command]
    else:
        argv = ['/usr/bin/bash', '-c', command]

    env = dict(os.environ)
    env['PATH'] = SYSTEM_PATH + ':' + env.get('PATH', '')

    log.info('Executando (root=%s): %s', as_root, command)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except FileNotFoundError as exc:
        log.error('Programa não encontrado ao executar %r: %s', command, exc)
        return Result(False, '', f'Programa não encontrado: {exc}')
    except subprocess.TimeoutExpired:
        log.error('Tempo esgotado ao executar %r', command)
        return Result(False, '',
                      f'O comando demorou mais de {timeout} segundos '
                      'e foi cancelado.')
    except Exception as exc:  # noqa: BLE001 - o erro precisa chegar ao usuário
        log.exception('Falha inesperada ao executar %r', command)
        return Result(False, '', f'Falha inesperada: {exc}')

    ok = proc.returncode == 0
    output = (proc.stdout or '').strip()
    error = (proc.stderr or '').strip()

    if ok:
        log.info('Concluído (código %s): %s', proc.returncode, command)
    else:
        log.warning('Falhou (código %s): %s -> %s',
                    proc.returncode, command, error)
        error = friendly_error(error) or (
            f'O comando terminou com código {proc.returncode}.')

    return Result(ok, output, error)
