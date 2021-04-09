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
        color = -1 if self.board.turn == chess.BLACK else 1
        if self.board.is_variant_loss():
            return color * -MATE_UPPER
        if self.board.is_variant_win():
            return color * MATE_UPPER
        if self.board.is_variant_draw():
            return 0
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
    # representation = ""
    # representation += str(board.pawns)
    # representation += str(board.knights)
    # representation += str(board.bishops)
    # representation += str(board.rooks)
    # representation += str(board.queens)
    # representation += str(board.kings)
    # representation += str(board.occupied_co[chess.WHITE])
    # representation += str(board.occupied_co[chess.BLACK])
    # representation += str(board.occupied)
    # representation += str(board.promoted)
    # representation += str(board.turn)
    # return hash(representation)
    # # return hash(''.join([move.uci() for move in board.move_stack]))
    return hash(board.epd())


# lower <= s(pos) <= upper
Entry = namedtuple('Entry', 'lower upper')


class Searcher:

    CHECK_TIME_AFTER_NODES = 200

    def __init__(self):
        self.tp_score = {}
        self.tp_move = {}
        self.nodes = 0
        self.best_move = None
        self._timeout = None
        self._cache = {}
        self.maxdepth = 3
        self.extradepth = 3
        self.score = 0

    def setTimeout(self, timeout=None):
        LOGGER.info("COnfiguring timeout to {}".format(timeout))
        if timeout is not None:
            self._timeout = time.process_time() + timeout
        else:
            self._timeout = None

    def checkTimeout(self, depth, alpha, beta):
        if self._timeout is not None and time.process_time() >= self._timeout:
            LOGGER.warning("Depth = {}, alpha={}, beta={}, nodes={}".format(depth, alpha, beta, self.nodes))
            raise TimoutException

    def log(self, msg, indent=0):
        LOGGER.debug(indent * " " + msg)

    def search(self, board, evaluation, maxdepth=1000, maxtime=None):
        """ Iterative deepening MTD-bi search """
        self.setTimeout(None)
        #depth, move, score = next(self._search(board, evaluation, 2))
        self.setTimeout(maxtime)
        # with chess.polyglot.open_reader("gm2001.bin") as reader:
        #     try:
        #         move = reader.choice(board)
        #         yield 0, move.move, 0
        #         return
        #     except IndexError:
        #         pass

        try:
            for depth, move, score, stack in self._search(board, evaluation, maxdepth):
                yield depth, move, score, stack
        except TimoutException:
            pass

    def minimax(self, pos, depth, alpha, beta, extra=0):

        maximizingPlayer = pos.board.turn == chess.WHITE
        epd = hashBoard(pos.board)
        depth = max(0, depth)

        if self.nodes % Searcher.CHECK_TIME_AFTER_NODES == 0:
            self.checkTimeout(depth, alpha, beta)
        #LOGGER.debug("Depth {}".format(depth))

        if pos.board.is_variant_loss():
            return (-MATE_UPPER if maximizingPlayer else MATE_UPPER, None, [])
        if pos.board.is_variant_win():
            return (MATE_UPPER if maximizingPlayer else -MATE_UPPER, None, [])
        if pos.board.is_variant_draw():
            return (0, None, [])

        try:
            entry, _depth, _move, _moves = self._cache[epd]
            if depth <= _depth:
                if entry.lower > beta:
                    return entry.lower, _move, _moves
                if entry.upper < alpha:
                    return entry.upper, _move, _moves

            else:
                entry = Entry(-MATE_UPPER, MATE_UPPER)
            # if depth <= _depth:
            #     return _score, move, moves
        except KeyError:
            entry = Entry(-MATE_UPPER, MATE_UPPER)



        self.nodes += 1

        def save(epd, score, depth, move, moveList):
            if score >= beta:
                newEntry = Entry(score, entry.upper)
            elif score <= alpha:
                newEntry = Entry(entry.lower, score)
            else:
                newEntry = entry
            # try:
            #     _, cachedDepth, _, _ = self._cache[epd]
            #     if cachedDepth <= depth:
            #          self._cache[epd] = (newEntry, depth, move, [move] + moveList)
            # except KeyError:
            self._cache[epd] = (newEntry, depth, move, [move] + moveList)

        best = -MATE_UPPER if maximizingPlayer else MATE_UPPER
        bestMove = None
        moveStack = []
        color = 1 if maximizingPlayer else -1

        def genMoves():
            score = pos.score
            if depth == 0:
                yield score, None, []

            try:
                _, _, killer_move, _ = self._cache[epd]
            except KeyError:
                killer_move = None

            moves = list(pos.board.legal_moves)
            data = { move: pos.value(move) for move in moves }
            def key(move):
                return data[move]
            sortedMoves = sorted(moves, key=key, reverse=maximizingPlayer)
            if killer_move:
                sortedMoves.insert(0, killer_move)
            for move in sortedMoves:
                if depth > 0 or color * data[move] > 200:
                    try:
                        pos.board.push(move)
                        bestScore, _, mvs = self.minimax(pos, depth-1, alpha, beta)
                    finally: # pop the move, even when there is a timeout
                        pos.board.pop()
                    yield bestScore, move, mvs

        for score, move, moves in genMoves():
            #print("--> ", move, moves, score, maximizingPlayer, best, alpha, beta)
            if maximizingPlayer:
                if score >= best:
                    bestMove = move
                    moveStack = moves
                best = max(best, score)
                alpha = max(alpha, score)
            else:
                if score <= best:
                    bestMove = move
                    moveStack = moves
                best = min(best, score)
                beta = min(beta, score)

            if alpha >= beta:
                #best = upper_bound
                bestMove = move
                LOGGER.info("Saving {} with score {}, depth={} ({} > {})".format(move, score, depth, alpha, beta))
                LOGGER.debug("Move stack 1 {}".format(pos.board.move_stack))
                #self._cache[hashBoard(pos.board)] = (best, depth, move, pos.board.fullmove_number)
                break
            LOGGER.info("Checking done at {}: {}, {}".format(depth, alpha, beta))

        save(epd, best, depth, bestMove, moveStack)
        return best, bestMove, [bestMove] + moveStack

    def get_variation(self, pos, depth):

        try:
            _, _, move, _ = self._cache[hashBoard(pos.board)]
            if move:
                try:
                    pos.board.push(move)
                    variation = self.get_variation(pos, depth-1)
                    variation.insert(0, move)
                    return variation
                finally:
                    pos.board.pop()
        except KeyError:
            pass
        return []

    def MTDF(self, pos, score, depth):
        g = score
        upperbound = MATE_UPPER
        lowerbound = -MATE_UPPER
        best = None
        moves = []
        while lowerbound < upperbound:
            if g == lowerbound:
                beta = g + 1
            else:
                beta = g

            g, best, moves = self.minimax(pos, depth, beta-1, beta)
            #print("MTDF: {}, {} , {} beta={}, positions={}".format(g, lowerbound, upperbound, beta, self.nodes))
            if g < beta:
                upperbound = g
            else:
                lowerbound = g
        return g, best, moves

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
            # alpha = -MATE_UPPER
            # beta = MATE_UPPER
            LOGGER.info("Trying depth {}".format(depth))
            #score, best, moves = self.minimax(pos, depth, alpha, beta)
            self.score, best, moves = self.MTDF(pos, self.score, depth)
            print(self.get_variation(pos, depth))
            yield depth, best, self.score, moves


def search(searcher, pos, secs, variant=None):
    """ Search for a position """
    eval_function = evaluation.get_evaluation_function(variant)

    try:
        for depth, move, score, moves in searcher.search(pos, eval_function, maxtime=secs):
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
        for _depth, move, score, stack in searcher.search(board, boardeval, maxdepth=10, maxtime=5):
            print(_depth, move, score, searcher.nodes, stack)
            # if time.time() - start > 2:
            #     break

        if score == MATE_UPPER:
            print("Checkmate!")

        # The black player moves from a rotated position, so we have to
        # 'back rotate' the move before printing it.
        print("My move:", board.san(move))
        board.push(move)
        print_pos(board)


if __name__ == '__main__':
    main()
