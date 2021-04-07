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

    #@functools.lru_cache(maxsize=None)
    def __call__(self, board, color):
        board = board.board
        score = 0
        score += bin(board.pawns & board.occupied_co[color]).count("1") * self._pieces[chess.PAWN]
        score += bin(board.knights & board.occupied_co[color]).count("1") * self._pieces[chess.KNIGHT]
        score += bin(board.bishops & board.occupied_co[color]).count("1") * self._pieces[chess.BISHOP]
        score += bin(board.rooks & board.occupied_co[color]).count("1") * self._pieces[chess.ROOK]
        score += bin(board.queens & board.occupied_co[color]).count("1") * self._pieces[chess.QUEEN]
        return score


def piece_activity(board, color):
    board = board.board
    score = 0
    attack_factor = {
        chess.PAWN: 0,
        chess.KNIGHT: 15,
        chess.BISHOP: 10,
        chess.ROOK: 5,
        chess.QUEEN: 3,
        chess.KING: 0
    }
    names = (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
    values = [board.knights, board.bishops, board.rooks, board.queens]
    for pieces, piece_type in [(chess.SquareSet(piece & board.occupied_co[color]), name) for piece, name in zip(values, names)]:
        for square in pieces:
            score += attack_factor[piece_type] * len(board.attacks(square))

    return score

def activity(board, square):
    attack_factor = {
        chess.PAWN: 2,
        chess.KNIGHT: 6,
        chess.BISHOP: 4,
        chess.ROOK: 3,
        chess.QUEEN:3,
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

class Space(object):

    def __call__(self, pos, color):
        # find the lowest piece that we attack
        score = 0
        my_pawns = pos.board.pawns & pos.board.occupied_co[color]
        for square in chess.SquareSet(my_pawns):
            if color == chess.BLACK:
                score += 7 - chess.square_rank(square)
            else:
                score += chess.square_rank(square)
        return 20*score

class Evaluation(object):
    def __init__(self):
        self.evals = []

    #@functools.lru_cache(maxsize=None)
    def __call__(self, pos):
        #pass
        # board = pos.board
        score = 0
        # for square in chess.SQUARES:

        #     def compute():
        #         partial_score = 0
        #         for ev in self.evals:
        #             partial_score += ev(board, square)
        #         return partial_score

        #     if board.color_at(square) == chess.WHITE:
        #         score += compute()
        #     elif board.color_at(square) == chess.BLACK:
        #         score -= compute()

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
        # self.evals = [
        #     #material(Classical.pieces),
        #     #attack_enemy_king,
        #     activity
        # ]

    def __call__(self, pos):

        score = super().__call__(pos)
        #score += MaterialBalance(Classical.pieces)(pos, chess.WHITE) - MaterialBalance(Classical.pieces)(pos, chess.BLACK)
        #score += Space()(pos, chess.WHITE) - Space()(pos, chess.BLACK)
        score += PsqtEval(pos, chess.WHITE) - PsqtEval(pos, chess.BLACK)
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

psqt = {
    chess.PAWN : (   0,   0,   0,   0,   0,   0,   0,   0,
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

pieces = { chess.PAWN: 100,
                chess.KNIGHT: 280,
                chess.BISHOP: 320,
                chess.ROOK: 479,
                chess.QUEEN: 929,
                chess.KING: 60000 }

def compute_diff(pos, score, move):
    def transform(idx):
        if pos.board.turn is chess.WHITE:
            return idx
        return 63-idx
    from_square = move.from_square
    to_square = move.to_square
    piece_type = pos.board.piece_type_at(from_square)
    score -= psqt[piece_type][transform(from_square)]
    score += psqt[piece_type][transform(to_square)]
    try:
        score += pieces[pos.board.piece_type_at(to_square)]
        score += psqt[pos.board.piece_type_at(to_square)][transform(to_square)]
    except KeyError:
        pass
    return score

def transform(square, color):
    rank = chess.square_rank(square)
    file = chess.square_file(square)
    if color == chess.WHITE:
        return 8*(7-rank) + file
    else:
        return 8*rank + (7 - file)


def PsqtEval(pos, color):
    board = pos.board
    if color == chess.WHITE:
        score = 0
        for square in chess.SquareSet(board.occupied_co[chess.WHITE]):
            piece = board.piece_type_at(square)

            score += psqt[piece][transform(square, chess.WHITE)] + pieces[piece]
        return score
    else:
        score = 0
        for square in chess.SquareSet(board.occupied_co[chess.BLACK]):
            piece = board.piece_type_at(square)
            score += psqt[piece][transform(square, chess.BLACK)] + pieces[piece]
        return score

    # if color == chess.BLACK:
    #     return evaluate(pos.board.mirror())
    # return evaluate(pos.board)