import unittest
import amwafish
import chess
import evaluation
import time
from parameterized import parameterized

class Dummy(object):
    def __call__(self, board, color): 
        score = 0 
        for piece in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KNIGHT):
            score += len(board.pieces(piece, color))
        return score

class MockEvaluation(evaluation.Classical):

    def __init__(self):
        super().__init__()
        self.evals = [evaluation.MaterialBalance(evaluation.Classical.pieces)]

def setUpPosition(fen):
    board = chess.Board(fen)
    pos = amwafish.Position(board, MockEvaluation(), depth=0)
    searcher = amwafish.Searcher()
    return pos, searcher

class TestSearch(unittest.TestCase):

    def test_bound(self):
        """Test the bound method in a lost position"""
        fen = "8/1pq1bk1p/2p1b3/3n4/3P4/2P2NP1/P1Q2P1P/R2QKB1R b KQ - 4 18"
        position, searcher = setUpPosition(fen)
        # best = searcher.bound(position, 0, 2)
        # #print(best, searcher.tp_move[position])
        # best = searcher.bound(position, position.score, 10)
        # print(best, searcher.tp_move[position])
        for depth, move, score in searcher.search(position.board, MockEvaluation(), maxdepth=3):
            print(depth, move, score)

    def _test_timeout(self):
        """Test timeout on game SKsTefjW"""
        fen = "r1b1k1nr/ppp2ppp/2np1q2/4p3/2B1P3/2NPB3/PPP1NbPP/R2Q1R1K b kq - 1 8"
        position, searcher = setUpPosition(fen)
        # best = searcher.bound(position, 0, 2)
        # #print(best, searcher.tp_move[position])
        # best = searcher.bound(position, position.score, 10)
        # print(best, searcher.tp_move[position])
        start = time.clock()
        for depth, move, score in searcher.search(position.board, evaluation.Classical(), maxdepth=10, maxtime=5):
            print(depth, move, score)
            print(searcher.nodes)
            #print(searcher.tp_move[position])
            end = time.clock()
            print("Time taken = ", end - start)
            start = end


class BlunderTest(unittest.TestCase):
    @parameterized.expand([
        ("r1bqkb1r/pppp1ppp/2n1pn2/8/3PP3/2N2N2/PPP2PPP/R1BQKB1R b KQkq - 0 4", ["f8d6"]),
        ("rnbqk1nr/pp2ppbp/6p1/2pp4/8/4N3/PPPPPPPP/RNBQKB1R w KQkq - 0 5", ["d2d4", "b1c3"])
    ])
    def test_position(self, fen, blunders):
        position, searcher = setUpPosition(fen)
        for depth, move, score in searcher.search(position.board, evaluation.Classical(), maxdepth=10, maxtime=5):
            print(searcher.nodes, depth, move, score)
        print(depth, move, score)
        self.assertNotIn(move, [chess.Move.from_uci(blunder) for blunder in blunders])


class BestMoveTest(unittest.TestCase):
    @parameterized.expand([
        ("r1bqk2r/pppp1ppp/3Ppn2/8/8/2N2Q2/PPP2PPP/R1B1KB1R b KQkq - 0 7", "c7d6")
    ])
    def test_position(self, fen, best):
        position, searcher = setUpPosition(fen)
        for depth, move, score in searcher.search(position.board, evaluation.Classical(), maxdepth=10, maxtime=5):
            print(searcher.nodes)
        print(move)
        self.assertEqual(move, chess.Move.from_uci(best))

if __name__ == "__main__":
    unittest.main()
