#!/usr/bin/env pypy
# -*- coding: utf-8 -*-

from __future__ import print_function
import re, sys, time
from itertools import count
from collections import namedtuple
import chess
import chess.svg
import chess.variant
import chess.polyglot
import random
import os
import evaluation
import concurrent.futures
import logging

LOGGER = logging.getLogger(__name__)

###############################################################################
# Piece-Square tables. Tune these to change sunfish's behaviour
###############################################################################

pieces = { chess.PAWN: 100,
          chess.KNIGHT: 280,
          chess.BISHOP: 320,
          chess.ROOK: 479,
          chess.QUEEN: 929,
          chess.KING: 60000 }



###############################################################################
# Global constants
###############################################################################

# Mate value must be greater than 8*queen + 2*(rook+knight+bishop)
# King value is set to twice this value such that if the opponent is
# 8 queens up, but we got the king, we still exceed MATE_VALUE.
# When a MATE is detected, we'll set the score to MATE_UPPER - plies to get there
# E.g. Mate in 3 will be MATE_UPPER - 6
MATE_LOWER = pieces[chess.KING] - 10*pieces[chess.QUEEN]
MATE_UPPER = pieces[chess.KING] + 10*pieces[chess.QUEEN]

# The table size is the maximum number of elements in the transposition table.
TABLE_SIZE = 1e7

# Constants for tuning search
QS_LIMIT = 219
EVAL_ROUGHNESS = 50
DRAW_TEST = True

###############################################################################
# Chess logic
###############################################################################

class Position(object):
    """ A state of a chess game
    board -- a 120 char representation of the board
    evaluation
    """
    def __init__(self, board, evalfunction=None, depth=0):
        if evalfunction is None:
            evalfunction = evaluation.Classical()
        self.board = board
        self.evaluation = evalfunction
        self.depth = depth
        self._score = None

    def gen_moves(self):
        for move in self.board.legal_moves:
            #board = self.move(move)
            yield move

    def rotate(self):
        ''' Rotates the board, preserving enpassant '''
        return Position(self.board.copy(), self.evaluation)

    def __hash__(self):
        return hash(self.board.epd())

    def __eq__(self, other):
        return hash(self) == hash(other)

    @property
    def score(self):
        return self.evaluation(self)


    def value(self, move):
        try:
            self.board.push(move)
            #print(self.score)
            #sign = -1 if self.board.turn is chess.BLACK else 1
            return self.score
        finally:
            self.board.pop()

    def move(self, move):
        board = self.board.copy()
        board.push(move)
        return Position(board, self.evaluation, self.depth+1)

    def __lt__(self, other):
        return self.score < other.score



###############################################################################
# Search logic
###############################################################################



class TimoutException(Exception):
    pass

def hashBoard(board):
    representation = ""
    representation += str(board.pawns)
    representation += str(board.knights)
    representation += str(board.bishops)
    representation += str(board.rooks)
    representation += str(board.queens)
    representation += str(board.kings)
    representation += str(board.occupied_co[chess.WHITE])
    representation += str(board.occupied_co[chess.BLACK])
    representation += str(board.occupied)
    representation += str(board.promoted)
    return hash(representation)
    # return hash(''.join([move.uci() for move in board.move_stack]))
    #return hash(board.epd())

# lower <= s(pos) <= upper
Entry = namedtuple('Entry', 'lower upper')


class Searcher:

    CHECK_TIME_AFTER_NODES = 5000

    def __init__(self):
        self.tp_score = {}
        self.tp_move = {}
        self.nodes = 0
        self.best_move = None
        self._timeout = None
        self._cache = {}

    def setTimeout(self, timeout=None):
        LOGGER.info("COnfiguring timeout to {}".format(timeout))
        if timeout is not None:
            self._timeout = time.process_time() + timeout
        else:
            self._timeout = None

    def checkTimeout(self):
        if self._timeout is not None and time.process_time() >= self._timeout:
            raise TimoutException

    def log(self, msg, indent=0):
        LOGGER.debug(indent * " " + msg)

    # secs over maxn is a breaking change. Can we do this?
    # I guess I could send a pull request to deep pink
    # Why include secs at all?
    def search(self, board, evaluation, maxdepth=1000, maxtime=None):
        """ Iterative deepening MTD-bi search """
        self.setTimeout(None)
        #depth, move, score = next(self._search(board, evaluation, 2))
        self.setTimeout(maxtime)
        with chess.polyglot.open_reader("gm2001.bin") as reader:
            try:
                move = reader.choice(board)
                yield 0, move.move, 0
                return
            except IndexError:
                pass

        try:
            for depth, move, score in self._search(board, evaluation, maxdepth):
                yield depth, move, score
        except TimoutException:
            yield depth, move, score

    def compute(self, pos):
        color = -1 if pos.board.turn == chess.BLACK else 1
        _score = pos.score
        LOGGER.debug("score={}, move = {}".format(color*_score, pos.board.peek()))
        score = color * _score
        self._cache[epd] = (_score, 0, pos.board.peek(), pos.board.fullmove_number)
        return score, pos.board.peek()

    def minimax(self, pos, depth, alpha, beta):

        maximizingPlayer = pos.board.turn == chess.WHITE
        epd = hashBoard(pos.board)

        if self.nodes % Searcher.CHECK_TIME_AFTER_NODES == 0:
            self.checkTimeout()
        #LOGGER.debug("Depth {}".format(depth))

        try:
            _score, _depth, move = self._cache[epd]
            if depth <= _depth:
                return _score, move
        except KeyError:
            pass
        self.nodes += 1


        if pos.board.is_variant_loss():
            return (-MATE_UPPER if maximizingPlayer else MATE_UPPER, None)
        if pos.board.is_variant_win():
            return (MATE_UPPER if maximizingPlayer else -MATE_UPPER, None)
        if pos.board.is_variant_draw():
            return (0, None)

        if depth == 0:
            _score = pos.score
            self._cache[epd] = (_score, 0, None)
            return _score, None


        # Run through the moves, shortcutting when possible
        moves = list(pos.board.legal_moves)
        def score(move):
            try:
                pos.board.push(move)
                return self.minimax(pos, depth=0, alpha=alpha, beta=beta)[0]
            finally:
                pos.board.pop()

        data = { move: score(move) for move in moves }
        def key(move):
            return data[move]
        sortedMoves = sorted(moves, key=key, reverse=maximizingPlayer)

        if depth == 1:
            try:
                move = sortedMoves[0]
                self._cache[epd] = (data[move], depth, move)
                return data[move], move
            except IndexError:
                pass

        # killer
        try:
            _,_, killer = self._cache[epd]
            if killer:
                sortedMoves.insert(0, killer)
        except KeyError:
            pass

        if maximizingPlayer:

            best = -MATE_UPPER
            bestMove = None

            LOGGER.info("Checking for white at depth {}: {}".format(depth, pos.board.move_stack))
            try:
                for move in sortedMoves:
                    try:
                        if pos.board.is_capture(move) and depth == 2:
                            newdepth = depth
                        else:
                            newdepth = depth - 1
                        pos.board.push(move)
                        LOGGER.info("White move {} at depth {}, alpha={}, beta={}".format(move, depth, alpha, beta))
                        result = self.minimax(pos, depth=newdepth, alpha=alpha, beta=beta)
                        score = result[0]
                    finally:
                        pos.board.pop()

                    if score >= best:
                        bestMove = move
                    best = max(best, score)
                    alpha = max(alpha, score)

                    if alpha >= beta:
                        #best = upper_bound
                        bestMove = move
                        LOGGER.info("Saving {} with score {}, depth={} ({} > {})".format(move, score, depth, alpha, beta))
                        LOGGER.debug("Move stack 1 {}".format(pos.board.move_stack))
                        #self._cache[hashBoard(pos.board)] = (best, depth, move, pos.board.fullmove_number)
                        break
                LOGGER.info("Checking for white done at {}: {}, {}".format(depth, alpha, beta))
                return best, bestMove
            finally:
                self._cache[epd] = (best, depth, bestMove)
        else:
            best = MATE_UPPER
            bestMove = None

            LOGGER.info("Checking for black at depth {}: {}".format(depth, pos.board.move_stack))
            try:
                for move in sortedMoves:
                    try:
                        if pos.board.is_capture(move) and depth == 2:
                            newdepth = depth
                        else:
                            newdepth = depth - 1
                        pos.board.push(move)
                        LOGGER.info("Black move {} at depth {}, alpha={}, beta={}".format(move, depth, alpha, beta))
                        result = self.minimax(pos, depth=newdepth, alpha=alpha, beta=beta)

                        score = result[0]
                    finally:
                        pos.board.pop()

                    if score <= best:
                        bestMove = move
                    best = min(best, score)
                    beta = min(beta, score)

                    if alpha >= beta:
                        #best = upper_bound
                        bestMove = move
                        LOGGER.info("Saving {} with score {}, depth={} ({} > {})".format(move, score, depth, alpha, beta))
                        LOGGER.debug("Move stack 1 {}".format(pos.board.move_stack))
                        #self._cache[hashBoard(pos.board)] = (best, depth, move, pos.board.fullmove_number)
                        break

                LOGGER.info("Checking for black done at {}: {}, {}".format(depth, alpha, beta))
                return best, bestMove
            finally:
                self._cache[epd] = (best, depth, bestMove)

        #return best

    def _search(self, board, evaluation, maxdepth=1000):
        pos = Position(board, evaluation, depth=0)
        self.nodes = 0
        #self.tp_score.clear()
        self.tp_move.clear()

        # In finished games, we could potentially go far enough to cause a recursion
        # limit exception. Hence we bound the ply.
        self._cache = {}
        self.cache_hits = 0
        # lower_bound = -MATE_UPPER
        # upper_bound = MATE_UPPER
        for depth in range(1, maxdepth):
            #self.tp_score.clear()
            # The inner loop is a binary search on the score of the position.
            # Inv: lower <= score <= upper
            # 'while lower != upper' would work, but play tests show a margin of 20 plays better.
            alpha = -MATE_UPPER
            beta = MATE_UPPER
            LOGGER.info("Trying depth {}".format(depth))
            score, best = self.minimax(pos, depth, alpha, beta)
            yield depth, best, score


def search(searcher, pos, secs, variant=None):
    """ Search for a position """
    eval_function = evaluation.get_evaluation_function(variant)

    try:
        for depth, move, score in searcher.search(pos, eval_function, maxtime=secs):
            LOGGER.info("Found move {} for depth {} with score {}".format(move, depth, score))
            yield depth, move, score
    except TimoutException:
        LOGGER.warning("Timeout in search function")
    #return depth, move, score

###############################################################################
# User interface
###############################################################################

def print_pos(board):
    print()
    print(board.unicode(invert_color=False))
    print()


def main():
    #logging.basicConfig(level=logging.INFO)
    board = chess.Board()
    boardeval = evaluation.Classical()
    searcher = Searcher()
    while True:
        #print_pos(board)

        if board.is_checkmate():
            print("You lost")
            break

        # We query the user until she enters a (pseudo) legal move.
        while True:
            inp = input('Your move: ')
            try:
                move = chess.Move.from_uci(inp)
                if move not in board.legal_moves:
                    raise ValueError
            except ValueError:
                print("{} is not a legal move".format(move))
            else:
                break

        board.push(move)

        # After our move we rotate the board and print it again.
        # This allows us to see the effect of our move.
        print_pos(board)

        if board.is_checkmate():
            print("You won")
            break

        # Fire up the engine to look for a move.
        start = time.time()
        for _depth, move, score in searcher.search(board, boardeval, maxtime=None):
            print(_depth, move, score, searcher.nodes)
            if time.time() - start > 2:
                break

        if score == MATE_UPPER:
            print("Checkmate!")

        # The black player moves from a rotated position, so we have to
        # 'back rotate' the move before printing it.
        print("My move:", board.san(move))
        board.push(move)
        print_pos(board)


if __name__ == '__main__':
    main()
