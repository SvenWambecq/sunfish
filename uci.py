#!/home/pi/amwafish/py3/bin/python -u
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
import chess.variant
import amwafish
import evaluation

from tools import Unbuffered

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('module', help='sunfish.py file (without .py)', type=str, default='amwafish', nargs='?')
    parser.add_argument('--tables', metavar='pst', help='alternative pst table', type=str, default=None)
    args = parser.parse_args()

    amwafish = importlib.import_module(args.module)
    #logging.basicConfig(filename='amwafish.log', level=logging.DEBUG)

    out = Unbuffered(sys.stdout)
    def output(line):
        print(line, file=out)
        logging.debug(line)
    pos = chess.Board()
    searcher = amwafish.Searcher()
    our_time, opp_time = 1000, 1000 # time in centi-seconds
    show_thinking = True
    options = {}
    eval_function = evaluation.get_evaluation_function()
    stack = []
    while True:
        logging.debug(f'>>> in loop ')
        if stack:
            smove = stack.pop()
        else: smove = input()

        logging.debug(f'>>> {smove} ')
        if smove.startswith('setoption'):
            optionMatcher = re.compile("setoption name (?P<name>.*) value (?P<value>.*)")
            match = optionMatcher.match(smove)
            if match:
                options[match.group("name")] = match.group("value")

        if smove == 'quit':
            break

        elif smove == 'uci':
            output('id name amwafish')
            output('id author Sven Wambecq')
            output('uciok')

        elif smove == 'isready':
            output('readyok')

        elif smove == 'ucinewgame':
            stack.append('position fen ' + chess.STARTING_FEN)

        elif smove.startswith('position fen'):
            _, _, data = smove.split(' ', 2)
            try: 
                _, moves = data.split('moves')
                moves = moves.strip().split(' ')
            except ValueError: 
                moves = []
            board = chess.variant.find_variant(options["UCI_Variant"])()
            eval_function = evaluation.get_evaluation_function(options["UCI_Variant"])
            for move in moves:
                board.push(chess.Move.from_uci(move))
            pos = board

        elif smove.startswith('position startpos'):
            params = smove.split(' ')
            pos = chess.Board()

            if len(params) > 2 and params[2] == 'moves':
                for move in params[3:]:
                    pos.push(chess.Move.from_uci(move))

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

            for sdepth, _move, _score in searcher.search(pos, eval_function, maxdepth=depth, maxtime=our_time/moves_remain/1000):
                pass
            else:
                if _move:
                    output('bestmove ' + _move.uci())

        elif smove.startswith('time'):
            our_time = int(smove.split()[1])

        elif smove.startswith('otim'):
            opp_time = int(smove.split()[1])

        else:
            pass

if __name__ == '__main__':
    main()

