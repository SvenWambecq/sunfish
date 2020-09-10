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

###############################################################################
# Piece-Square tables. Tune these to change sunfish's behaviour
###############################################################################

pieces = { chess.PAWN: 100, 
          chess.KNIGHT: 280, 
          chess.BISHOP: 320, 
          chess.ROOK: 479, 
          chess.QUEEN: 929, 
          chess.KING: 60000 }
pst = {
    chess.PAWN: (   0,   0,   0,   0,   0,   0,   0,   0,
            78,  83,  86,  73, 102,  82,  85,  90,
             7,  29,  21,  44,  40,  31,  44,   7,
           -17,  16,  -2,  15,  14,   0,  15, -13,
           -26,   3,  10,   9,   6,   1,   0, -23,
           -22,   9,   5, -11, -10,  -2,   3, -19,
           -31,   8,  -7, -37, -36, -14,   3, -31,
             0,   0,   0,   0,   0,   0,   0,   0),
    chess.KNIGHT: ( -66, -53, -75, -75, -10, -55, -58, -70,
            -3,  -6, 100, -36,   4,  62,  -4, -14,
            10,  67,   1,  74,  73,  27,  62,  -2,
            24,  24,  45,  37,  33,  41,  25,  17,
            -1,   5,  31,  21,  22,  35,   2,   0,
           -18,  10,  13,  22,  18,  15,  11, -14,
           -23, -15,   2,   0,   2,   0, -23, -20,
           -74, -23, -26, -24, -19, -35, -22, -69),
    chess.BISHOP: ( -59, -78, -82, -76, -23,-107, -37, -50,
           -11,  20,  35, -42, -39,  31,   2, -22,
            -9,  39, -32,  41,  52, -10,  28, -14,
            25,  17,  20,  34,  26,  25,  15,  10,
            13,  10,  17,  23,  17,  16,   0,   7,
            14,  25,  24,  15,   8,  25,  20,  15,
            19,  20,  11,   6,   7,   6,  20,  16,
            -7,   2, -15, -12, -14, -15, -10, -10),
    chess.ROOK: (  35,  29,  33,   4,  37,  33,  56,  50,
            55,  29,  56,  67,  55,  62,  34,  60,
            19,  35,  28,  33,  45,  27,  25,  15,
             0,   5,  16,  13,  18,  -4,  -9,  -6,
           -28, -35, -16, -21, -13, -29, -46, -30,
           -42, -28, -42, -25, -25, -35, -26, -46,
           -53, -38, -31, -26, -29, -43, -44, -53,
           -30, -24, -18,   5,  -2, -18, -31, -32),
    chess.QUEEN: (   6,   1,  -8,-104,  69,  24,  88,  26,
            14,  32,  60, -10,  20,  76,  57,  24,
            -2,  43,  32,  60,  72,  63,  43,   2,
             1, -16,  22,  17,  25,  20, -13,  -6,
           -14, -15,  -2,  -5,  -1, -10, -20, -22,
           -30,  -6, -13, -11, -16, -11, -16, -27,
           -36, -18,   0, -19, -15, -15, -21, -38,
           -39, -30, -31, -13, -31, -36, -34, -42),
    chess.KING: (   4,  54,  47, -99, -99,  60,  83, -62,
           -32,  10,  55,  56,  56,  55,  10,   3,
           -62,  12, -57,  44, -67,  28,  37, -31,
           -55,  50,  11,  -4, -19,  13,   0, -49,
           -55, -43, -52, -28, -51, -47,  -8, -50,
           -47, -42, -43, -79, -64, -32, -29, -32,
            -4,   3, -14, -50, -57, -18,  13,   4,
            17,  30,  -3, -14,   6,  -1,  40,  18),
}


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
EVAL_ROUGHNESS = 13
DRAW_TEST = True


###############################################################################
# Chess logic
###############################################################################

class Position(namedtuple('Position', 'board')):
    """ A state of a chess game
    board -- a 120 char representation of the board
    evaluation
    """

    def gen_moves(self):
        for move in self.board.legal_moves:
            yield move

    def rotate(self):
        ''' Rotates the board, preserving enpassant '''
        return Position(self.board.copy())

    def __hash__(self):
        return hash(self.board.fen())

    CENTER = chess.SquareSet([chess.C3, chess.D3, chess.E3, chess.E3, 
                              chess.C4, chess.D4, chess.E4, chess.F4,
                              chess.C5, chess.D5, chess.E5, chess.F5, 
                              chess.C6, chess.D6, chess.E6, chess.F6])
    def _compute_score(self, color):
        score = 0
        
        for piece in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING):
            for square in self.board.pieces(piece, color):
                score += pieces[piece]
                #score += pst[piece][idx(square)]
                score += 10 * len(self.board.attacks(square))
                if square in Position.CENTER: 
                    score += 30
        # check passed pawn 
        pawns = self.board.pieces(chess.PAWN, color)
        for pawn in pawns:
            if color is chess.WHITE:
                score += 0.4 * chess.square_rank(pawn)
            else:
                score += 0.4 * (8 - chess.square_rank(pawn))
        return score

    @property
    def score(self):
        if self.board.turn is chess.WHITE:
            return self._compute_score(chess.WHITE) - self._compute_score(chess.BLACK)
        else:
            return self._compute_score(chess.BLACK) - self._compute_score(chess.WHITE)

    def value(self, move):
        try: 
            self.board.push(move)
            self.board.push(chess.Move.null())
            return self.score
        finally:
            self.board.pop()
            self.board.pop()

    def nullmove(self):
        ''' Like rotate, but clears ep and kp '''
        board = self.board.copy()
        board.push(chess.Move.null())
        return Position(board)

    def move(self, move):
        board = self.board.copy()
        board.push(move)
        return Position(board)

    def __lt__(self, other):
        return self.score < other.score



###############################################################################
# Search logic
###############################################################################

# lower <= s(pos) <= upper
Entry = namedtuple('Entry', 'lower upper')

class Searcher:
    def __init__(self):
        self.tp_score = {}
        self.tp_move = {}
        self.history = set()
        self.nodes = 0
        self.best_move = None

    def bound(self, pos, gamma, depth, root=True):
        """ returns r where
                s(pos) <= r < gamma    if gamma > s(pos)
                gamma <= r <= s(pos)   if gamma <= s(pos)"""
        self.nodes += 1

        # Depth <= 0 is QSearch. Here any position is searched as deeply as is needed for
        # calmness, and from this point on there is no difference in behaviour depending on
        # depth, so so there is no reason to keep different depths in the transposition table.
        depth = max(depth, 0)

        # Sunfish is a king-capture engine, so we should always check if we
        # still have a king. Notice since this is the only termination check,
        # the remaining code has to be comfortable with being mated, stalemated
        # or able to capture the opponent king.
        if pos.board.is_variant_loss():
            return -MATE_UPPER
        if pos.board.is_variant_win():
            return MATE_UPPER
        if pos.board.is_variant_draw():
            return 0

        # Look in the table if we have already searched this position before.
        # We also need to be sure, that the stored search was over the same
        # nodes as the current search.
        entry = self.tp_score.get((pos, depth+pos.board.fullmove_number*2), Entry(-MATE_UPPER, MATE_UPPER))
        if entry.lower >= gamma and (not root or self.tp_move.get(pos) is not None):
            return entry.lower
        if entry.upper < gamma:
            return entry.upper

        # Here extensions may be added
        # Such as 'if in_check: depth += 1'

        # Generator of moves to search in order.
        # This allows us to define the moves, but only calculate them if needed.
        def moves():
            # First try not moving at all. We only do this if there is at least one major piece left on the board, since otherwise zugzwangs are too dangerous.
            # if depth > 0 and not root and any(c in pos.board for c in 'RBNQ'):
            #     yield None, -self.bound(pos.nullmove(), 1-gamma, depth-3, root=False)
            # For QSearch we have a different kind of null-move, namely we can just stop and not capture anythign else.
            if depth == 0:
                yield None, pos.score
            # Then killer move. We search it twice, but the tp will fix things for us. Note, we don't have to check for legality, since we've already done it before. Also note that in QS the killer must be a capture, otherwise we will be non deterministic.
            killer = self.tp_move.get(pos)
            if killer and (depth > 0 or pos.value(killer) >= QS_LIMIT):
                yield killer, -self.bound(pos.move(killer), 1-gamma, depth-1, root=False)
            # Then all the other moves
            for move in sorted(pos.gen_moves(), key=pos.value, reverse=True):
                #print('_____')
                #print(depth, move, pos.value(move))
                # If depth == 0 we only try moves with high intrinsic score (captures and promotions). Otherwise we do all moves.
                if depth > 0 or pos.value(move) >= QS_LIMIT:
                    yield move, -self.bound(pos.move(move), 1-gamma, depth-1, root=False)

        # Run through the moves, shortcutting when possible
        best = -MATE_UPPER
        for move, score in moves():
            best = max(best, score)
            if best >= gamma:
                # Clear before setting, so we always have a value
                if len(self.tp_move) > TABLE_SIZE: self.tp_move.clear()
                # Save the move for pv construction and killer heuristic
                self.tp_move[pos] = move
                break

        # Clear before setting, so we always have a value
        if len(self.tp_score) > TABLE_SIZE: self.tp_score.clear()
        # Table part 2
        if best >= gamma:
            self.tp_score[(pos, depth+pos.board.fullmove_number*2)] = Entry(best, entry.upper)
        if best < gamma:
            self.tp_score[(pos, depth+pos.board.fullmove_number*2)] = Entry(entry.lower, best)
        return best

    # secs over maxn is a breaking change. Can we do this?
    # I guess I could send a pull request to deep pink
    # Why include secs at all?
    def search(self, pos, history=()):
        """ Iterative deepening MTD-bi search """
        self.nodes = 0
        #self.tp_score.clear()
        self.tp_move.clear()

        # In finished games, we could potentially go far enough to cause a recursion
        # limit exception. Hence we bound the ply.
        for depth in range(1, 1000):
            # The inner loop is a binary search on the score of the position.
            # Inv: lower <= score <= upper
            # 'while lower != upper' would work, but play tests show a margin of 20 plays better.
            lower, upper = -MATE_UPPER, MATE_UPPER
            while lower < upper - EVAL_ROUGHNESS:
                gamma = (lower+upper+1)//2
                score = self.bound(pos, gamma, depth)
                #print(depth, score, gamma)
                if score >= gamma:
                    lower = score
                if score < gamma:
                    upper = score
            # We want to make sure the move to play hasn't been kicked out of the table,
            # So we make another call that must always fail high and thus produce a move.
            self.bound(pos, lower, depth)
            # If the game hasn't finished we can retrieve our move from the
            # transposition table.
            yield depth, self.tp_move.get(pos), self.tp_score.get((pos, depth+pos.board.fullmove_number*2)).lower


###############################################################################
# User interface
###############################################################################

def print_pos(board):
    print()
    print(board.unicode(invert_color=False))
    print()


def main():
    board = chess.Board()
    #board = chess.variant.AntichessBoard()
    hist = [Position(chess.Board())]
    searcher = Searcher()
    while True:
        print_pos(board)

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
        for _depth, move, score in searcher.search(Position(board)):
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
