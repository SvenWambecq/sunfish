import chess
import functools

def get_evaluation_function(variant=None):
    if variant is None or variant == 'standard':
        return Classical()
    elif variant == 'suicide' or variant == 'giveaway' or variant == 'antichess':
        return Antichess()
    elif variant == 'crazyhouse':
        return Classical()
    else:
        return Classical()
        #raise TypeError('Unsupported variant {}'.format(variant))


def attack_enemy_king(board, color):
    score = 0
    enemy_king = board.king(not color)
    for offset in [9, 8, 7, 1, -9, -8, -7, -1]:
        target_square = enemy_king + offset 
        if 0 <= target_square < 64: 
            if board.is_attacked_by(color, target_square):
                score += 30 
    return score



class MaterialBalance(object):

    def __init__(self, pieces):
        self._pieces = pieces
    
    @functools.lru_cache(maxsize=None)
    def __call__(self, board, color):
        board = board.board
        score = 0
        for piece in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
            for _ in board.pieces(piece, color):
                score += self._pieces[piece]
        return score
    

@functools.lru_cache(maxsize=None)
def piece_activity(board, color):
    board = board.board
    score = 0
    attack_factor = {
        chess.PAWN: 10,
        chess.KNIGHT: 10,
        chess.BISHOP: 10,
        chess.ROOK: 5,
        chess.QUEEN: 5,
        chess.KING: 1
    }
    for piece in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING):
        for square in board.pieces(piece, color):
            score += attack_factor[piece] * len(board.attacks(square))
    return score

def activity(board, square):
    attack_factor = {
        chess.PAWN: 2,
        chess.KNIGHT: 3,
        chess.BISHOP: 3,
        chess.ROOK: 1,
        chess.QUEEN:1,
        chess.KING: 1
    }
    try:
        return attack_factor[board.piece_type_at(square)] * len(board.attacks(square))
    except KeyError:
        return 0


class material(object):
    def __init__(self, pieces):
        self._pieces = pieces

    def __call__(self, board, square):
        try:
            return self._pieces[board.piece_type_at(square)]
        except KeyError:
            return 0


class Evaluation(object):
    def __init__(self):
        self.evals = []

    #@functools.lru_cache(maxsize=None)
    def __call__(self, pos):
        board = pos.board
        score = 0 
        for square in chess.SQUARES:
            
            def compute():
                partial_score = 0 
                for ev in self.evals: 
                    partial_score += ev(board, square)
                return partial_score

            if board.color_at(square) == chess.WHITE:
                score += compute()
            elif board.color_at(square) == chess.BLACK:
                score -= compute()

        return score #if pos.board.turn is chess.WHITE else -score

class Classical(Evaluation):
    pieces = { chess.PAWN: 100, 
                chess.KNIGHT: 280, 
                chess.BISHOP: 320, 
                chess.ROOK: 479, 
                chess.QUEEN: 929, 
                chess.KING: 60000 }

    def __init__(self):
        super().__init__()
        self.evals = [
            material(Classical.pieces), 
            #attack_enemy_king, 
            activity
        ]

    def __call__(self, pos):
        score = super().__call__(pos)
        #score += piece_activity(pos, chess.WHITE) - piece_activity(pos, chess.BLACK)
        return score

class MinimumPieceToCapture(object):
    def __init__(self, pieces):
        self._pieces = pieces

    def __call__(self, pos, color):
        # find the lowest piece that we attack 
        score = 0 
        for piece in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING):
            for square in pos.board.pieces(piece, not color):
                if pos.board.is_attacked_by(color, square):
                    # we attack the given piece at square
                    score = max(score, self._pieces[piece])
        return score

class Antichess(Evaluation):
    pieces = { chess.PAWN: -100, 
                chess.KNIGHT: -300, 
                chess.BISHOP: -300, 
                chess.ROOK: -500, 
                chess.QUEEN: -1000, 
                chess.KING: -300 }

    def __init__(self):
        super().__init__()
        self.evals = [
            material(Antichess.pieces), 
            
        ]
        self.minPiece = MinimumPieceToCapture(Antichess.pieces)
    def __call__(self, pos):
        score = super().__call__(pos)
        score += self.minPiece(pos, chess.WHITE) - self.minPiece(pos, chess.BLACK)
        return score