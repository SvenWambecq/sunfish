import unittest
import amwafish
import chess

class TestCrazyHouse(unittest.TestCase):

    def setUp(self):
        self._searcher = amwafish.Searcher()

    def test_endofGame(self):
        """Test hang in game tFeolSyZ"""
        fen = "rnb1kbnr/pppp1ppp/4B3/4p3/4P3/5N2/PPPP1PPP/RNB1K2R/QQ b KQkq - 0 5"
        board = chess.variant.CrazyhouseBoard(fen)
        board.pockets[chess.WHITE].add(chess.QUEEN)
        board.pockets[chess.WHITE].add(chess.QUEEN)
        move, score, depth = amwafish.search(self._searcher, board, 1, variant="crazyhouse")
        self.assertEqual(move, chess.Move.from_uci('d7e6'))

if __name__ == "__main__":
    unittest.main()