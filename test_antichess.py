import unittest
import amwafish
import chess

class TestAntiChess(unittest.TestCase):

    def setUp(self):
        self._searcher = amwafish.Searcher()

    def test_endofGame(self):
        """Test that amwafish handles the last moves properly"""
        fen = "6R1/8/8/8/1p6/8/N1P4P/6NR w - - 0 22"
        board = chess.variant.AntichessBoard(fen)
        depth, move, score = next(amwafish.search(self._searcher, board, 0.01, variant="giveaway"))
        self.assertEqual(move, chess.Move.from_uci('a2b4'))

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    unittest.main()