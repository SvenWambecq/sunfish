import chess

def get_evaluation_function(variant=None):
    if variant is None or variant == 'standard':
        return Classical()
    elif variant == 'suicide' or variant == 'giveaway' or variant == 'antichess':
        return Antichess()
    elif variant == 'crazyhouse':
        return Classical()
    else:
        raise TypeError('Unsupported variant {}'.format(variant))


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
    
    def __call__(self, board, color):
        score = 0
        for piece in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
            for _ in board.pieces(piece, color):
                score += self._pieces[piece]
        return score
    

def piece_activity(board, color):
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

class Evaluation(object):
    def __init__(self):
        self.evals = []

    def __call__(self, board):
        score = 0 
        for evaluation in self.evals: 
            score += evaluation(board, board.turn) - evaluation(board, not board.turn)
        return score



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
            MaterialBalance(Classical.pieces), 
            attack_enemy_king, 
            piece_activity
        ]

class MinimumPieceToCapture(object):
    def __init__(self, pieces):
        self._pieces = pieces

    def __call__(self, board, color):
        # find the lowest piece that we attack 
        score = 0 
        for piece in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING):
            for square in board.pieces(piece, not color):
                if board.is_attacked_by(color, square):
                    # we attack the given piece at square
                    score = min(score, self._pieces[piece])
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
            MaterialBalance(Antichess.pieces), 
            MinimumPieceToCapture(Antichess.pieces)
        ]
