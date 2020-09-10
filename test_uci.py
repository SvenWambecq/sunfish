import chess
import chess.engine

engine = chess.engine.SimpleEngine.popen_uci(["C:\\Users\\wambecq\\venvs\\Test37\\Scripts\\python", "-u", "uci.py"])

board = chess.Board()
while not board.is_game_over():
    result = engine.play(board, chess.engine.Limit(depth=4))
    board.push(result.move)
    print(board.unicode())

engine.quit()