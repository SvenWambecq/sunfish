#!/usr/bin/env pypy
# -*- coding: utf-8 -*-

from __future__ import print_function
import re, sys, time
from itertools import count
from collections import namedtuple
import chess
import chess.svg
import chess.variant
import random
import os
import evaluation
import concurrent.futures
from cachetools import cached
from cachetools.keys import hashkey
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

    def setTimeout(self, timeout=None):
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
        self.setTimeout(maxtime)
        try:
            for depth, move, score in self._search(board, evaluation, maxdepth):
                yield depth, move, score
        except TimoutException:
            pass

    def negamax(self, pos, depth, lower_bound, upper_bound):
        try:
            ev, d = self._cache[pos.board.epd()]
            if d >= depth: 
                self.cache_hits += 1
                LOGGER.debug("return cached value {}".format(ev))
                return ev
        except KeyError: 
            pass 
        
        self.nodes += 1
        color = -1 if pos.board.turn == chess.BLACK else 1
        # if self.nodes % Searcher.CHECK_TIME_AFTER_NODES == 0:
        #     self.checkTimeout()
        LOGGER.debug("Depth {}".format(depth))
        # Depth <= 0 is QSearch. Here any position is searched as deeply as is needed for
        # calmness, and from this point on there is no difference in behaviour depending on
        # depth, so so there is no reason to keep different depths in the transposition table.
        if depth == 0: 
            LOGGER.debug("depth = 0, score={}".format(pos.score))
            score = color * pos.score
            self._cache[pos.board.epd()] = (score, 0)
            return score

        if pos.board.is_variant_loss():
            LOGGER.debug("Variant loss")
            return -color * MATE_UPPER
        if pos.board.is_variant_win():
            LOGGER.debug("Variant win")
            return color * MATE_UPPER
        if pos.board.is_variant_draw():
            LOGGER.debug("Variant draw")
            return 0
        # Run through the moves, shortcutting when possible

       # move = None
        mvs = []
        best = -MATE_UPPER
        lower = lower_bound
        upper = upper_bound
        try: 
            moves = pos.gen_moves()
            for move in moves: 
                try:
                    if pos.board.is_capture(move):
                        pos.board.push(move)
                        score = -self.negamax(pos, depth-1, -upper_bound, -lower_bound)
                        LOGGER.debug("Move {} = {}".format(move, score))
                        best = max(best, score)
                        lower_bound = max(lower_bound, score)
                    
                        if lower_bound > upper_bound:
                            best = upper_bound
                            LOGGER.debug("Saving {} with score {}".format(move, score))
                            return best
                    
                finally: 
                    if pos.board.is_capture(move):
                        pos.board.pop()

            for move in sorted(pos.gen_moves(), key=pos.value, reverse=pos.board.turn == chess.WHITE):
                try: 
                    is_capture = pos.board.is_capture(move)
                    pos.board.push(move)
                    score = -self.negamax(pos, depth-1, -upper_bound, -lower_bound)
                    LOGGER.debug("Move {} = {}".format(move, score))
                    best = max(best, score)
                    lower_bound = max(lower_bound, score)
                    
                    if lower_bound > upper_bound:
                        best = upper_bound
                        LOGGER.debug("Saving {} with score {}".format(move, score))
                        break
                    
                finally: 
                    pos.board.pop()

            return best
        finally: 
            self._cache[pos.board.epd()] = (best, depth)
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
        moves = {move: pos.value(move) for move in pos.gen_moves()}
        for depth in range(1, maxdepth):
            #self.tp_score.clear()
            # The inner loop is a binary search on the score of the position.
            # Inv: lower <= score <= upper
            # 'while lower != upper' would work, but play tests show a margin of 20 plays better.
            lower_bound = -MATE_UPPER
            upper_bound = MATE_UPPER
            LOGGER.info("Trying depth {}".format(depth))
            filtered = sorted(moves.items(), key=lambda item: item[1], reverse=pos.board.turn == chess.WHITE)
            for move, initial_score in filtered:
                try:
                    pos.board.push(move)
                    LOGGER.info("Evaluating Move {} initial score={}".format(move, initial_score))
                    score = -self.negamax(pos, depth, lower_bound, upper_bound)

                    LOGGER.info("Move {} = {} lower_bound = {} nodes={}".format(move, score, lower_bound, self.nodes))
                    if score >= lower_bound:
                        LOGGER.info("Found best move {} = {}".format(move, score))
                        moves[move] = score
                        lower_bound = score
                        best = move
                        #yield depth, best, score
                finally:
                    pos.board.pop()
            # lower, upper = -MATE_UPPER*2, MATE_UPPER*2
            #print("cache hits = {}".format(self.cache_hits))
            yield depth, best, score
            

def search(searcher, pos, secs, variant=None):
    """ Search for a position """
    eval_function = evaluation.get_evaluation_function(variant)
    try:
        for depth, move, score in searcher.search(pos, eval_function, maxtime=secs):
            yield depth, move, score
    except TimoutException:
        pass
    #return depth, move, score

###############################################################################
# User interface
###############################################################################

def print_pos(board):
    print()
    print(board.unicode(invert_color=False))
    print()


def main():
    logging.basicConfig(level=logging.DEBUG)
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
        for _depth, move, score in searcher.search(board, boardeval):
            #print(_depth, move, score)
            if time.time() - start > 2:
                break

        if score == MATE_UPPER:
            print("Checkmate!")

        # The black player moves from a rotated position, so we have to
        # 'back rotate' the move before printing it.
        print("My move:", board.san(move))
        board.push(move)


if __name__ == '__main__':
    main()
