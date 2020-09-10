#!/usr/bin/env pypy -u
# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import division
import importlib
import re
import sys
import time
import logging
import argparse

import tools
import chess
import amwafish

from tools import WHITE, BLACK, Unbuffered

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('module', help='sunfish.py file (without .py)', type=str, default='amwafish', nargs='?')
    parser.add_argument('--tables', metavar='pst', help='alternative pst table', type=str, default=None)
    args = parser.parse_args()

    amwafish = importlib.import_module(args.module)
    logging.basicConfig(filename='amwafish.log', level=logging.DEBUG)

    out = Unbuffered(sys.stdout)
    def output(line):
        print(line, file=out)
        logging.debug(line)
    pos = chess.Board(tools.FEN_INITIAL)
    searcher = amwafish.Searcher()
    color = WHITE
    our_time, opp_time = 1000, 1000 # time in centi-seconds
    show_thinking = True

    stack = []
    while True:
        if stack:
            smove = stack.pop()
        else: smove = input()

        logging.debug(f'>>> {smove} ')

        if smove == 'quit':
            break

        elif smove == 'uci':
            output('id name amwafish')
            output('id author Thomas Ahle & Contributors')
            output('uciok')

        elif smove == 'isready':
            output('readyok')

        elif smove == 'ucinewgame':
            stack.append('position fen ' + tools.FEN_INITIAL)

        elif smove.startswith('position fen'):
            _, _, fen = smove.split(' ', 2)
            pos = tools.parseFEN(fen)
            color = WHITE if fen.split()[1] == 'w' else BLACK

        elif smove.startswith('position startpos'):
            params = smove.split(' ')
            pos = amwafish.Position(chess.Board())
            color = WHITE

            if len(params) > 2 and params[2] == 'moves':
                for move in params[3:]:
                    pos = pos.move(chess.Move.from_uci(move))

        elif smove.startswith('go'):
            #  default options
            depth = 1000
            movetime = -1

            _, *params = smove.split(' ')
            for param, val in zip(*2*(iter(params),)):
                if param == 'depth':
                    depth = int(val)
                if param == 'movetime':
                    movetime = int(val)
                if param == 'wtime':
                    our_time = int(val)
                if param == 'btime':
                    opp_time = int(val)

            moves_remain = 40

            start = time.time()
            ponder = None
            for sdepth, _move, _score in searcher.search(pos):
                # moves = tools.pv(searcher, pos, include_scores=False)

                # if show_thinking:
                #     entry = searcher.tp_score.get((pos, sdepth, True))
                #     score = int(round((entry.lower + entry.upper)/2))
                #     usedtime = int((time.time() - start) * 1000)
                #     moves_str = moves if len(moves) < 15 else ''
                #     output('info depth {} score cp {} time {} nodes {} pv {}'.format(sdepth, score, usedtime, searcher.nodes, moves_str))

                # if len(moves) > 5:
                #     ponder = moves[1]

                if movetime > 0 and (time.time() - start) * 1000 > movetime:
                    output('bestmove ' + _move.uci())
                    break

                if (time.time() - start) * 1000 > our_time/moves_remain:
                    output('bestmove ' + _move.uci())
                    break

                if sdepth >= depth:
                    output('bestmove ' + _move.uci())
                    break


        elif smove.startswith('time'):
            our_time = int(smove.split()[1])

        elif smove.startswith('otim'):
            opp_time = int(smove.split()[1])

        else:
            pass

if __name__ == '__main__':
    main()

