import unittest
import amwafish
import chess
import evaluation

def setUpPosition(fen):
    board = chess.Board(fen)
    pos = amwafish.Position(board, evaluation.Classical(), depth=0)
    searcher = amwafish.Searcher()
    return pos, searcher

positions = [
        ("r1bqkb1r/pppp1ppp/2n1pn2/8/3PP3/2N2N2/PPP2PPP/R1BQKB1R b KQkq - 0 4", ["f8d6"]),
        ("rnbqk1nr/pp2ppbp/6p1/2pp4/8/4N3/PPPPPPPP/RNBQKB1R w KQkq - 0 5", ["d2d4", "b1c3"])
    ]

def test_position(fen, blunders):
    position, searcher = setUpPosition(fen)
    for depth, move, score in searcher.search(position.board, evaluation.Classical(), maxdepth=6, maxtime=10):
        print(searcher.nodes, depth, move, score)
    print(depth, move, score)
    
import logging
logging.basicConfig(level=logging.INFO)
test_position(*positions[0])
#test_position("rnbqk1nr/pp2ppbp/6p1/2pp4/8/4N3/PPPPPPPP/RNBQKB1R w KQkq - 0 5", ["d2d4", "b1c3"])