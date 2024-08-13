#include "testlib.h"

using namespace std;

int main(int argc, char **argv) {
    registerValidation(argc, argv);
    while(!inf.eof()) inf.skipChar();
    
    inf.readEof();
}