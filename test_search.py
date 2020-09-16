import unittest
import amwafish
import chess
import evaluation
import time

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

class TestSearch(unittest.TestCase):

    def setUpPosition(self, fen):
        board = chess.Board(fen)
        pos = amwafish.Position(board, MockEvaluation(), depth=0)
        searcher = amwafish.Searcher()
        return pos, searcher


    def test_bound(self):
        """Test the bound method in a lost position"""
        fen = "8/1pq1bk1p/2p1b3/3n4/3P4/2P2NP1/P1Q2P1P/R2QKB1R b KQ - 4 18"
        position, searcher = self.setUpPosition(fen)
        # best = searcher.bound(position, 0, 2)
        # #print(best, searcher.tp_move[position])
        # best = searcher.bound(position, position.score, 10)
        # print(best, searcher.tp_move[position])
        for depth, move, score in searcher.search(position.board, MockEvaluation(), maxdepth=3):
            print(depth, move, score)

    def test_timeout(self):
        """Test timeout on game SKsTefjW"""
        fen = "r1b1k1nr/ppp2ppp/2np1q2/4p3/2B1P3/2NPB3/PPP1NbPP/R2Q1R1K b kq - 1 8"
        position, searcher = self.setUpPosition(fen)
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

if __name__ == "__main__":
    unittest.main()
